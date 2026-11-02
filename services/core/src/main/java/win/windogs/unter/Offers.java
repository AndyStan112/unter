package win.windogs.unter;

import jakarta.validation.Valid;
import java.math.BigDecimal;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import win.windogs.unter.Trips.*;

@RestController
public class Offers {
    private final JdbcTemplate db;
    private final Dispatch dispatch;
    private final Pricing pricing;
    public Offers(JdbcTemplate db, Dispatch dispatch, Pricing pricing) { this.db=db; this.dispatch=dispatch; this.pricing=pricing; }

    public record Offer(UUID id, UUID tripId, UUID driverId, String status, Instant createdAt, Instant expiresAt, Instant respondedAt) {}
    public record OfferEvent(Trip trip, Offer offer) {}
    public record DriverOffer(Offer offer, Trip trip, BigDecimal estimatedPrice) {}

    static Offer map(ResultSet rs, int row) throws SQLException {
        return new Offer(rs.getObject("id",UUID.class),rs.getObject("trip_id",UUID.class),rs.getObject("driver_id",UUID.class),
                rs.getString("status"),Rows.time(rs,"created_at"),Rows.time(rs,"expires_at"),Rows.time(rs,"responded_at"));
    }
    static Offer load(JdbcTemplate db, UUID id) {
        return db.query("SELECT * FROM offers WHERE id=?",Offers::map,id).stream().findFirst().orElseThrow(()->Errors.notFound("Offer"));
    }

    /** Drivers poll this; 204 means there's nothing to answer right now. */
    @GetMapping("/drivers/{id}/offer") public ResponseEntity<DriverOffer> current(@PathVariable UUID id) {
        Drivers.load(db,id);
        List<Offer> pending=db.query("SELECT * FROM offers WHERE driver_id=? AND status='PENDING' AND expires_at > now()",Offers::map,id);
        if (pending.isEmpty()) return ResponseEntity.noContent().build();
        Trip trip=Trips.load(db,pending.get(0).tripId());
        return ResponseEntity.ok(new DriverOffer(pending.get(0),trip,pricing.price(trip.pickup(),trip.dropoff(),pricing.surge(trip.zone()))));
    }
    @PostMapping("/offers/{id}/accept") public OfferEvent accept(@PathVariable UUID id, @Valid @RequestBody ByDriver by) {
        return dispatch.accept(id,by.driverId());
    }
    @PostMapping("/offers/{id}/reject") public Offer reject(@PathVariable UUID id, @Valid @RequestBody ByDriver by) {
        return dispatch.reject(id,by.driverId());
    }
}
