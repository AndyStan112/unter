package win.windogs.unter;

import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class Zones {
    private final JdbcTemplate db;
    public Zones(JdbcTemplate db) { this.db=db; }
    public record Zone(String name, double lat, double lon) {}
    public record Position(double lat, double lon) {}
    /** A coordinate in a request body. */
    public record Point(@NotNull @DecimalMin("-90") @DecimalMax("90") Double lat,
                        @NotNull @DecimalMin("-180") @DecimalMax("180") Double lon) {}

    @GetMapping("/zones") public List<Zone> zones() {
        return db.query("SELECT name,lat,lon FROM zones ORDER BY name",(rs,i)->new Zone(rs.getString("name"),rs.getDouble("lat"),rs.getDouble("lon")));
    }
    /** A point belongs to the zone with the nearest center; there are few zones, so compare them all. */
    public String nearest(double lat, double lon) {
        return zones().stream().min(Comparator.comparingDouble(z->distanceKm(lat,lon,z.lat(),z.lon()))).orElseThrow().name();
    }
    public static double distanceKm(double lat1, double lon1, double lat2, double lon2) {
        double dLat=Math.toRadians(lat2-lat1), dLon=Math.toRadians(lon2-lon1);
        double a=Math.pow(Math.sin(dLat/2),2)+Math.cos(Math.toRadians(lat1))*Math.cos(Math.toRadians(lat2))*Math.pow(Math.sin(dLon/2),2);
        return 6371*2*Math.asin(Math.sqrt(a));
    }
}
