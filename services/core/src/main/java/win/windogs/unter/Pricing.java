package win.windogs.unter;

import java.math.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import win.windogs.unter.Zones.Position;

/** Fare = (5.00 RON + 2.50 RON per booked road km (straight-line fallback when unavailable)) × the pickup zone's surge multiplier. */
@Component
public class Pricing {
    static final BigDecimal BASE=new BigDecimal("5.00"), PER_KM=new BigDecimal("2.50"), NO_SURGE=new BigDecimal("1.00");
    private final JdbcTemplate db;
    public Pricing(JdbcTemplate db) { this.db=db; }

    /** The newest surge rule active in the zone right now, or no surge. */
    public BigDecimal surge(String zone) {
        return db.queryForList("SELECT multiplier FROM surge_rules WHERE zone=? AND starts_at <= now() AND ends_at > now() ORDER BY created_at DESC LIMIT 1",
                BigDecimal.class,zone).stream().findFirst().orElse(NO_SURGE);
    }
    public BigDecimal price(Position pickup, Position dropoff, BigDecimal surge) {
        BigDecimal km=BigDecimal.valueOf(Zones.distanceKm(pickup.lat(),pickup.lon(),dropoff.lat(),dropoff.lon()));
        return price(km.doubleValue()*1000,surge);
    }
    public BigDecimal price(double distanceMeters, BigDecimal surge) {
        return BASE.add(PER_KM.multiply(BigDecimal.valueOf(distanceMeters/1000))).multiply(surge).setScale(2,RoundingMode.HALF_UP);
    }
}
