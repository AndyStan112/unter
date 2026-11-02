package win.windogs.unter;

import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import win.windogs.unter.Drivers.StatusEvent;
import win.windogs.unter.Offers.*;
import win.windogs.unter.Trips.*;

/**
 * Matching and every offer transition.
 *
 * Correctness never depends on this running once, on one thread or on one instance: each decisive step
 * is a conditional UPDATE ("... WHERE status = 'AVAILABLE'") that exactly one transaction can win, and
 * the losers see 0 rows changed and move on. Rows are always locked in the same order (trip, then offer,
 * then driver), so two transactions can never wait on each other forever.
 */
@Component
public class Dispatch {
    private static final Logger log=LoggerFactory.getLogger(Dispatch.class);
    private final JdbcTemplate db;
    private final TransactionTemplate tx, fresh;
    private final Outbox outbox;
    private final Pricing pricing;
    private final int offerSeconds, matchSeconds, positionSeconds;

    public Dispatch(JdbcTemplate db, PlatformTransactionManager transactions, Outbox outbox, Pricing pricing,
                    @Value("${unter.offer-timeout-seconds}") int offerSeconds, @Value("${unter.match-timeout-seconds}") int matchSeconds,
                    @Value("${unter.position-max-age-seconds}") int positionSeconds) {
        this.db=db; this.outbox=outbox; this.pricing=pricing;
        this.tx=new TransactionTemplate(transactions);
        this.fresh=new TransactionTemplate(transactions);
        fresh.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        this.offerSeconds=offerSeconds; this.matchSeconds=matchSeconds; this.positionSeconds=positionSeconds;
    }

    record Candidate(UUID id, double km) {}

    /** Offers a waiting trip to the nearest free driver, if there is one. Safe to call anytime, from anywhere. */
    public void tryMatch(UUID tripId) {
        try {
            fresh.executeWithoutResult(status->{ if (!offer(tripId)) status.setRollbackOnly(); });
        } catch (RuntimeException e) { log.warn("Matching a trip failed, will retry: {}",e.getClass().getSimpleName()); }
    }
    private boolean offer(UUID tripId) {
        // Claim the trip first: if it's no longer waiting (cancelled, or another matcher was faster), stop.
        List<Trip> claimed=db.query("UPDATE trips SET status='OFFERED' WHERE id=? AND status='REQUESTED' RETURNING *",Trips::map,tripId);
        if (claimed.isEmpty()) return false;
        Trip trip=claimed.get(0);
        for (Candidate driver:candidates(trip)) {
            // The decisive step: only one transaction can move this driver out of AVAILABLE.
            if (db.update("UPDATE drivers SET status='OFFERED', current_trip_id=?, updated_at=now() WHERE id=? AND status='AVAILABLE'",
                    trip.id(),driver.id())==0) continue;
            Offer offer=db.query("INSERT INTO offers(id,trip_id,driver_id,expires_at) VALUES (?,?,?,now()+make_interval(secs => ?)) RETURNING *",
                    Offers::map,UUID.randomUUID(),trip.id(),driver.id(),offerSeconds).get(0);
            outbox.add("trip.offered",new OfferEvent(trip,offer));
            driverChanged(driver.id(),"AVAILABLE");
            return true;
        }
        return false;  // nobody free: rolling back puts the trip back to REQUESTED for the next sweep
    }
    /** Free drivers that are still sending their position, nearest first, never one who already had this trip. */
    private List<Candidate> candidates(Trip trip) {
        return db.query("""
                SELECT id, lat, lon FROM drivers
                WHERE status='AVAILABLE' AND position_updated_at > now()-make_interval(secs => ?)
                  AND id NOT IN (SELECT driver_id FROM offers WHERE trip_id=?)""",
                (rs,i)->new Candidate(rs.getObject("id",UUID.class),
                        Zones.distanceKm(trip.pickup().lat(),trip.pickup().lon(),rs.getDouble("lat"),rs.getDouble("lon"))),
                positionSeconds,trip.id()).stream().sorted(Comparator.comparingDouble(Candidate::km)).limit(10).toList();
    }

    public OfferEvent accept(UUID offerId, UUID driverId) {
        return tx.execute(status->{
            Offer offer=ownOffer(offerId,driverId);
            lockTrip(offer.tripId());
            // Accepting and expiring test the same condition; whichever commits first wins, the other changes nothing.
            List<Offer> accepted=db.query("UPDATE offers SET status='ACCEPTED', responded_at=now() WHERE id=? AND status='PENDING' AND expires_at > now() RETURNING *",
                    Offers::map,offerId);
            if (accepted.isEmpty()) throw ended(Offers.load(db,offerId));
            Trip trip=Trips.load(db,offer.tripId());
            BigDecimal surge=pricing.surge(trip.zone());
            Trip assigned=db.query("UPDATE trips SET status='ASSIGNED', driver_id=?, assigned_at=now(), surge_multiplier=?, price=? WHERE id=? AND status='OFFERED' RETURNING *",
                    Trips::map,driverId,surge,pricing.price(trip.pickup(),trip.dropoff(),surge),trip.id()).get(0);
            if (db.update("UPDATE drivers SET status='ON_TRIP', updated_at=now() WHERE id=? AND status='OFFERED' AND current_trip_id=?",driverId,trip.id())==0)
                throw new IllegalStateException("Driver is not holding this offer");
            outbox.add("trip.assigned",new TripEvent(assigned));
            driverChanged(driverId,"OFFERED");
            return new OfferEvent(assigned,accepted.get(0));
        });
    }
    public Offer reject(UUID offerId, UUID driverId) {
        return tx.execute(status->{
            Offer offer=ownOffer(offerId,driverId);
            return release(offer,"REJECTED","AVAILABLE").orElseThrow(()->ended(Offers.load(db,offerId)));
        });
    }
    /** A driver going offline gives up their pending offer, if any. Runs in the caller's transaction. */
    public boolean releaseDriver(UUID driverId) {
        List<Offer> pending=db.query("SELECT * FROM offers WHERE driver_id=? AND status='PENDING'",Offers::map,driverId);
        return !pending.isEmpty() && release(pending.get(0),"REJECTED","OFFLINE").isPresent();
    }
    /** Ends a pending offer and puts its trip back in the queue; the driver becomes `driverStatus`. */
    private Optional<Offer> release(Offer offer, String outcome, String driverStatus) {
        lockTrip(offer.tripId());
        String onlyIfExpired=outcome.equals("EXPIRED") ? " AND expires_at <= now()" : "";
        List<Offer> ended=db.query("UPDATE offers SET status=?, responded_at=CASE WHEN ?::text='REJECTED' THEN now() END WHERE id=? AND status='PENDING'"+onlyIfExpired+" RETURNING *",
                Offers::map,outcome,outcome,offer.id());
        if (ended.isEmpty()) return Optional.empty();
        Trip waiting=db.query("UPDATE trips SET status='REQUESTED' WHERE id=? AND status='OFFERED' RETURNING *",Trips::map,offer.tripId()).get(0);
        db.update("UPDATE drivers SET status=?, current_trip_id=NULL, updated_at=now() WHERE id=? AND status='OFFERED' AND current_trip_id=?",
                driverStatus,offer.driverId(),offer.tripId());
        outbox.add(outcome.equals("EXPIRED") ? "trip.offer_expired" : "trip.offer_rejected",new OfferEvent(waiting,ended.get(0)));
        driverChanged(offer.driverId(),"OFFERED");
        return Optional.of(ended.get(0));
    }
    /** Lets go of whoever holds the trip (offered or assigned), when it's cancelled or completed. The caller holds the trip lock. */
    void freeDriver(UUID tripId) {
        db.update("UPDATE offers SET status='EXPIRED' WHERE trip_id=? AND status='PENDING'",tripId);
        List<Map<String,Object>> freed=db.queryForList("""
                UPDATE drivers d SET status='AVAILABLE', current_trip_id=NULL, updated_at=now()
                FROM (SELECT id, status AS old FROM drivers WHERE current_trip_id=? FOR UPDATE) o
                WHERE d.id=o.id RETURNING d.id, o.old""",tripId);
        for (Map<String,Object> row:freed) driverChanged((UUID)row.get("id"),(String)row.get("old"));
    }

    /** Every second: expire unanswered offers, give up on trips waiting too long, retry the rest. */
    @Scheduled(fixedDelay=1000)
    public void sweep() {
        for (UUID offer:ids("SELECT id FROM offers WHERE status='PENDING' AND expires_at <= now() ORDER BY expires_at LIMIT 100"))
            safely(()->tx.executeWithoutResult(s->release(Offers.load(db,offer),"EXPIRED","AVAILABLE")));
        for (UUID trip:ids("SELECT id FROM trips WHERE status='REQUESTED' AND requested_at <= now()-make_interval(secs => ?) LIMIT 100",matchSeconds))
            safely(()->tx.executeWithoutResult(s->giveUp(trip)));
        for (UUID trip:ids("SELECT id FROM trips WHERE status='REQUESTED' ORDER BY requested_at LIMIT 100"))
            tryMatch(trip);
    }
    private void giveUp(UUID tripId) {
        for (Trip trip:db.query("UPDATE trips SET status='UNMATCHED' WHERE id=? AND status='REQUESTED' RETURNING *",Trips::map,tripId))
            outbox.add("trip.unmatched",new TripEvent(trip));
    }

    private Offer ownOffer(UUID offerId, UUID driverId) {
        Offer offer=Offers.load(db,offerId);
        if (!offer.driverId().equals(driverId)) throw Errors.conflict("not_your_offer","Offer belongs to another driver");
        return offer;
    }
    private static Errors.ApiException ended(Offer offer) {
        // Still PENDING here means it ran out of time but the sweep hasn't released it yet.
        return Set.of("PENDING","EXPIRED").contains(offer.status()) ? Errors.conflict("offer_expired","Offer has expired")
                : Errors.conflict("offer_not_pending","Offer is "+offer.status());
    }
    private void lockTrip(UUID tripId) { db.queryForList("SELECT id FROM trips WHERE id=? FOR UPDATE",tripId); }
    private void driverChanged(UUID driverId, String previous) {
        outbox.add("driver.status_changed",new StatusEvent(Drivers.load(db,driverId),previous));
    }
    private List<UUID> ids(String sql, Object... args) {
        try { return db.queryForList(sql,UUID.class,args); }
        catch (RuntimeException e) { log.warn("Dispatch sweep failed, retrying: {}",e.getClass().getSimpleName()); return List.of(); }
    }
    private static void safely(Runnable step) {
        try { step.run(); } catch (RuntimeException e) { log.warn("Dispatch step failed, retrying: {}",e.getClass().getSimpleName()); }
    }
}
