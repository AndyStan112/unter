package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.*;
import win.windogs.unter.Zones.*;

@RestController
public class Trips {
    static final Set<String> STATUSES=Set.of("REQUESTED","OFFERED","ASSIGNED","PICKED_UP","COMPLETED","CANCELLED","UNMATCHED");
    private final JdbcTemplate db;
    private final TransactionTemplate tx;
    private final Outbox outbox;
    private final Dispatch dispatch;
    private final Zones zones;
    public Trips(JdbcTemplate db, PlatformTransactionManager transactions, Outbox outbox, Dispatch dispatch, Zones zones) {
        this.db=db; this.tx=new TransactionTemplate(transactions); this.outbox=outbox; this.dispatch=dispatch; this.zones=zones;
    }

    public record Trip(UUID id, UUID riderId, UUID driverId, String zone, Position pickup, Position dropoff, String status,
                       BigDecimal surgeMultiplier, BigDecimal price, Instant requestedAt, Instant assignedAt,
                       Instant pickedUpAt, Instant completedAt, Instant cancelledAt) {}
    public record TripEvent(Trip trip) {}
    public record NewTrip(@NotNull UUID riderId, @NotNull @Valid Point pickup, @NotNull @Valid Point dropoff) {}
    public record ByRider(@NotNull UUID riderId) {}
    public record ByDriver(@NotNull UUID driverId) {}

    static Trip map(ResultSet rs, int row) throws SQLException {
        return new Trip(rs.getObject("id",UUID.class),rs.getObject("rider_id",UUID.class),rs.getObject("driver_id",UUID.class),rs.getString("zone"),
                new Position(rs.getDouble("pickup_lat"),rs.getDouble("pickup_lon")),new Position(rs.getDouble("dropoff_lat"),rs.getDouble("dropoff_lon")),
                rs.getString("status"),rs.getBigDecimal("surge_multiplier"),rs.getBigDecimal("price"),Rows.time(rs,"requested_at"),
                Rows.time(rs,"assigned_at"),Rows.time(rs,"picked_up_at"),Rows.time(rs,"completed_at"),Rows.time(rs,"cancelled_at"));
    }
    static Trip load(JdbcTemplate db, UUID id) {
        return db.query("SELECT * FROM trips WHERE id=?",Trips::map,id).stream().findFirst().orElseThrow(()->Errors.notFound("Trip"));
    }
    /** Locks the trip row: every change to a trip, its offers and its driver starts here (see Dispatch). */
    private Trip lock(UUID id) {
        return db.query("SELECT * FROM trips WHERE id=? FOR UPDATE",Trips::map,id).stream().findFirst().orElseThrow(()->Errors.notFound("Trip"));
    }
    private Trip update(String sql, Object... args) { return db.query(sql,Trips::map,args).get(0); }

    @PostMapping("/trips") @ResponseStatus(HttpStatus.CREATED)
    public Trip create(@Valid @RequestBody NewTrip trip) {
        UUID id=UUID.randomUUID();
        tx.executeWithoutResult(status->{
            if (db.queryForObject("SELECT count(*) FROM riders WHERE id=?",Integer.class,trip.riderId())==0)
                throw Errors.badRequest("unknown_rider","Unknown rider");
            try {
                db.update("INSERT INTO trips(id,rider_id,zone,pickup_lat,pickup_lon,dropoff_lat,dropoff_lon) VALUES (?,?,?,?,?,?,?)",
                        id,trip.riderId(),zones.nearest(trip.pickup().lat(),trip.pickup().lon()),
                        trip.pickup().lat(),trip.pickup().lon(),trip.dropoff().lat(),trip.dropoff().lon());
            } catch (DuplicateKeyException e) { throw Errors.conflict("rider_has_open_trip","Rider already has an open trip"); }
            outbox.add("trip.requested",new TripEvent(load(db,id)));
        });
        // Look for a driver straight away; if nobody is free, the background sweep keeps trying.
        dispatch.tryMatch(id);
        return load(db,id);
    }
    @GetMapping("/trips/{id}") public Trip get(@PathVariable UUID id) { return load(db,id); }
    @GetMapping("/trips") public List<Trip> list(@RequestParam(required=false) String status, @RequestParam(required=false) String zone,
                                                 @RequestParam(defaultValue="50") int limit) {
        if (status!=null && !STATUSES.contains(status)) throw Errors.badRequest("invalid_request","Unknown trip status");
        if (limit<1 || limit>200) throw Errors.badRequest("invalid_request","limit must be between 1 and 200");
        return db.query("SELECT * FROM trips WHERE (?::text IS NULL OR status=?) AND (?::text IS NULL OR zone=?) ORDER BY requested_at DESC LIMIT ?",
                Trips::map,status,status,zone,zone,limit);
    }

    @PostMapping("/trips/{id}/cancel") @Transactional
    public Trip cancel(@PathVariable UUID id, @Valid @RequestBody ByRider by) {
        Trip trip=lock(id);
        if (!trip.riderId().equals(by.riderId())) throw Errors.conflict("not_your_trip","Trip belongs to another rider");
        if (!Set.of("REQUESTED","OFFERED","ASSIGNED").contains(trip.status())) throw Errors.conflict("trip_not_cancellable","Trip is "+trip.status());
        Trip cancelled=update("UPDATE trips SET status='CANCELLED', cancelled_at=now() WHERE id=? RETURNING *",id);
        outbox.add("trip.cancelled",new TripEvent(cancelled));
        dispatch.freeDriver(trip.id());
        return cancelled;
    }
    @PostMapping("/trips/{id}/pickup") @Transactional
    public Trip pickup(@PathVariable UUID id, @Valid @RequestBody ByDriver by) {
        Trip trip=driversTrip(id,by.driverId(),"ASSIGNED");
        Trip picked=update("UPDATE trips SET status='PICKED_UP', picked_up_at=now() WHERE id=? RETURNING *",trip.id());
        outbox.add("trip.picked_up",new TripEvent(picked));
        return picked;
    }
    @PostMapping("/trips/{id}/complete") @Transactional
    public Trip complete(@PathVariable UUID id, @Valid @RequestBody ByDriver by) {
        Trip trip=driversTrip(id,by.driverId(),"PICKED_UP");
        Trip completed=update("UPDATE trips SET status='COMPLETED', completed_at=now() WHERE id=? RETURNING *",trip.id());
        outbox.add("trip.completed",new TripEvent(completed));
        dispatch.freeDriver(trip.id());
        return completed;
    }
    private Trip driversTrip(UUID id, UUID driverId, String expected) {
        Trip trip=lock(id);
        if (!driverId.equals(trip.driverId())) throw Errors.conflict("not_your_trip","Trip is not assigned to this driver");
        if (!trip.status().equals(expected)) throw Errors.conflict("trip_not_"+expected.toLowerCase(),"Trip is "+trip.status());
        return trip;
    }
}
