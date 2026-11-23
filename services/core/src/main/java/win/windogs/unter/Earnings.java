package win.windogs.unter;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class Earnings {
    private final JdbcTemplate db;
    public Earnings(JdbcTemplate db) { this.db=db; }

    /** Called inside the trip completion transaction, never from a message consumer. */
    void settle(Trips.Trip trip) {
        db.update("INSERT INTO driver_earnings(trip_id,driver_id,fare,bonus) VALUES (?,?,?,?) ON CONFLICT (trip_id) DO NOTHING",
                trip.id(),trip.driverId(),trip.price(),trip.driverBonus());
    }

    @GetMapping("/drivers/{id}/earnings")
    public Map<String,Object> earnings(@PathVariable UUID id) {
        Drivers.load(db,id);
        Map<String,Object> totals=db.queryForMap("""
            SELECT count(*) AS completed_trips, coalesce(sum(fare),0) AS fares,
              coalesce(sum(bonus),0) AS bonuses, coalesce(sum(total),0) AS balance,
              coalesce(sum(total) FILTER (WHERE settled_at >= date_trunc('day',now() AT TIME ZONE 'Europe/Bucharest') AT TIME ZONE 'Europe/Bucharest'),0) AS today
            FROM driver_earnings WHERE driver_id=?""",id);
        Map<String,Object> result=new LinkedHashMap<>(totals);
        result.put("currency","RON"); result.put("mode","mock");
        result.put("entries",db.queryForList("SELECT * FROM driver_earnings WHERE driver_id=? ORDER BY settled_at DESC, trip_id LIMIT 50",id));
        return result;
    }
}
