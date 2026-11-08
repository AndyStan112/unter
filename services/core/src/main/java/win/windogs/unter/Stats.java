package win.windogs.unter;

import java.math.BigDecimal;
import java.sql.*;
import java.time.*;
import java.time.format.DateTimeParseException;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * Read-only aggregates for the surge/incentive analysis (MCP server and agent). Every query runs in a
 * READ ONLY transaction, and the callers' READER login can only send GET requests (see Auth).
 *
 * Trips are counted in the bucket of their requested_at, by pickup zone (trips.zone). The dropoff zone
 * is derived the same way core derives zones: the nearest center (Zones.nearest). Buckets are aligned to
 * UTC; empty buckets are returned with zeros so a quiet period is visible as such.
 */
@RestController
@Transactional(readOnly=true)
public class Stats {
    static final Duration MAX_WINDOW=Duration.ofDays(7);
    static final Map<String,String> BUCKETS=Map.of("15m","15 minutes","1h","1 hour","6h","6 hours","1d","1 day");
    private final NamedParameterJdbcTemplate db;
    private final int positionSeconds;
    public Stats(NamedParameterJdbcTemplate db, @Value("${unter.position-max-age-seconds}") int positionSeconds) {
        this.db=db; this.positionSeconds=positionSeconds;
    }

    public record ZoneBucket(String zone, Instant bucket,
            long requests, long assigned, long completed, long cancelled, long unmatched, long open,
            Double unmatchedRate, Double cancelRate, Double avgWaitS, Double p90WaitS, BigDecimal avgPrice, long arrivals,
            long offers, long offersAccepted, long offersRejected, long offersExpired, long driversOffered,
            Double offerRejectRate, Double offerExpiryRate) {}
    public record ZoneStats(Instant from, Instant to, String bucket, List<ZoneBucket> rows) {}
    public record Flow(String origin, String destination, long trips, long completed) {}
    public record Flows(Instant from, Instant to, List<Flow> flows) {}
    public record Supply(String zone, long available, long offered, long onTrip, long stale, long waitingTrips) {}
    public record SupplySnapshot(Instant asOf, int positionMaxAgeSeconds, List<Supply> zones) {}

    /** Trips requested in [from, to), each with its bucket, wait time and dropoff zone. */
    private static final String TRIPS="""
            t AS (
              SELECT t.*, date_bin(CAST(:step AS interval), t.requested_at, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS bucket,
                     EXTRACT(EPOCH FROM t.assigned_at - t.requested_at) AS wait_s, d.name AS dropoff_zone
              FROM trips t
              CROSS JOIN LATERAL (
                SELECT name FROM zones z
                ORDER BY asin(sqrt(power(sin(radians(z.lat - t.dropoff_lat) / 2), 2)
                         + cos(radians(t.dropoff_lat)) * cos(radians(z.lat)) * power(sin(radians(z.lon - t.dropoff_lon) / 2), 2))), name
                LIMIT 1) d
              WHERE t.requested_at >= :from AND t.requested_at < :to
            )""";

    @GetMapping("/stats/zones")
    public ZoneStats zones(@RequestParam(required=false) String from, @RequestParam(required=false) String to,
                           @RequestParam(defaultValue="1h") String bucket, @RequestParam(required=false) String zone) {
        String step=BUCKETS.get(bucket);
        if (step==null) throw Errors.badRequest("invalid_request","bucket must be one of "+new TreeSet<>(BUCKETS.keySet()));
        Window w=window(from,to);
        MapSqlParameterSource params=w.params().addValue("step",step).addValue("zone",knownZone(zone));
        List<ZoneBucket> rows=db.query("WITH "+TRIPS+"""
                , z AS (SELECT name FROM zones WHERE CAST(:zone AS text) IS NULL OR name = CAST(:zone AS text)),
                b AS (SELECT s AS bucket FROM generate_series(date_bin(CAST(:step AS interval), CAST(:from AS timestamptz),
                        TIMESTAMPTZ '2000-01-01 00:00:00+00'), CAST(:to AS timestamptz), CAST(:step AS interval)) s
                      WHERE s < :to),
                p AS (
                  SELECT zone, bucket, count(*) AS requests,
                         count(*) FILTER (WHERE assigned_at IS NOT NULL) AS assigned,
                         count(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                         count(*) FILTER (WHERE status = 'CANCELLED') AS cancelled,
                         count(*) FILTER (WHERE status = 'UNMATCHED') AS unmatched,
                         count(*) FILTER (WHERE status IN ('REQUESTED','OFFERED','ASSIGNED','PICKED_UP')) AS open,
                         round(avg(wait_s), 1) AS avg_wait_s,
                         round(CAST(percentile_cont(0.9) WITHIN GROUP (ORDER BY wait_s) AS numeric), 1) AS p90_wait_s,
                         round(avg(price) FILTER (WHERE status = 'COMPLETED'), 2) AS avg_price
                  FROM t GROUP BY zone, bucket),
                a AS (SELECT dropoff_zone AS zone, bucket, count(*) AS arrivals FROM t WHERE status = 'COMPLETED' GROUP BY 1, 2),
                o AS (
                  SELECT t.zone, t.bucket, count(*) AS offers,
                         count(*) FILTER (WHERE o.status = 'ACCEPTED') AS offers_accepted,
                         count(*) FILTER (WHERE o.status = 'REJECTED') AS offers_rejected,
                         count(*) FILTER (WHERE o.status = 'EXPIRED') AS offers_expired,
                         count(DISTINCT o.driver_id) AS drivers_offered
                  FROM offers o JOIN t ON t.id = o.trip_id GROUP BY 1, 2)
                SELECT z.name AS zone, b.bucket,
                       coalesce(p.requests, 0) AS requests, coalesce(p.assigned, 0) AS assigned,
                       coalesce(p.completed, 0) AS completed, coalesce(p.cancelled, 0) AS cancelled,
                       coalesce(p.unmatched, 0) AS unmatched, coalesce(p.open, 0) AS open,
                       round(p.unmatched::numeric / NULLIF(p.requests, 0), 3) AS unmatched_rate,
                       round(p.cancelled::numeric / NULLIF(p.requests, 0), 3) AS cancel_rate,
                       p.avg_wait_s, p.p90_wait_s, p.avg_price, coalesce(a.arrivals, 0) AS arrivals,
                       coalesce(o.offers, 0) AS offers, coalesce(o.offers_accepted, 0) AS offers_accepted,
                       coalesce(o.offers_rejected, 0) AS offers_rejected, coalesce(o.offers_expired, 0) AS offers_expired,
                       coalesce(o.drivers_offered, 0) AS drivers_offered,
                       round(o.offers_rejected::numeric / NULLIF(o.offers, 0), 3) AS offer_reject_rate,
                       round(o.offers_expired::numeric / NULLIF(o.offers, 0), 3) AS offer_expiry_rate
                FROM z CROSS JOIN b
                LEFT JOIN p ON p.zone = z.name AND p.bucket = b.bucket
                LEFT JOIN a ON a.zone = z.name AND a.bucket = b.bucket
                LEFT JOIN o ON o.zone = z.name AND o.bucket = b.bucket
                ORDER BY z.name, b.bucket""",params,(rs,i)->new ZoneBucket(rs.getString("zone"),Rows.time(rs,"bucket"),
                rs.getLong("requests"),rs.getLong("assigned"),rs.getLong("completed"),rs.getLong("cancelled"),
                rs.getLong("unmatched"),rs.getLong("open"),number(rs,"unmatched_rate"),number(rs,"cancel_rate"),
                number(rs,"avg_wait_s"),number(rs,"p90_wait_s"),rs.getBigDecimal("avg_price"),rs.getLong("arrivals"),
                rs.getLong("offers"),rs.getLong("offers_accepted"),rs.getLong("offers_rejected"),rs.getLong("offers_expired"),
                rs.getLong("drivers_offered"),number(rs,"offer_reject_rate"),number(rs,"offer_expiry_rate")));
        return new ZoneStats(w.from().toInstant(),w.to().toInstant(),bucket,rows);
    }

    /** Pickup zone to dropoff zone counts over the window, every pair included. */
    @GetMapping("/stats/flows")
    public Flows flows(@RequestParam(required=false) String from, @RequestParam(required=false) String to) {
        Window w=window(from,to);
        List<Flow> flows=db.query("WITH "+TRIPS+"""
                SELECT o.name AS origin, d.name AS destination,
                       count(t.id) AS trips, count(t.id) FILTER (WHERE t.status = 'COMPLETED') AS completed
                FROM zones o CROSS JOIN zones d
                LEFT JOIN t ON t.zone = o.name AND t.dropoff_zone = d.name
                GROUP BY o.name, d.name ORDER BY o.name, d.name""",w.params().addValue("step","1 hour"),
                (rs,i)->new Flow(rs.getString("origin"),rs.getString("destination"),rs.getLong("trips"),rs.getLong("completed")));
        return new Flows(w.from().toInstant(),w.to().toInstant(),flows);
    }

    /**
     * Drivers per zone right now. "available" only counts drivers dispatch could actually use: AVAILABLE with a
     * position newer than unter.position-max-age-seconds. "stale" counts online drivers without such a position.
     * "waiting_trips" are trips in the zone still looking for a driver. History isn't stored, so this is a snapshot.
     */
    @GetMapping("/stats/supply")
    public SupplySnapshot supply() {
        MapSqlParameterSource params=new MapSqlParameterSource("age",positionSeconds);
        List<Supply> zones=db.query("""
                SELECT z.name AS zone,
                       count(d.id) FILTER (WHERE d.status = 'AVAILABLE' AND d.position_updated_at > now() - make_interval(secs => :age)) AS available,
                       count(d.id) FILTER (WHERE d.status = 'OFFERED') AS offered,
                       count(d.id) FILTER (WHERE d.status = 'ON_TRIP') AS on_trip,
                       count(d.id) FILTER (WHERE d.status = 'AVAILABLE' AND (d.position_updated_at IS NULL
                                           OR d.position_updated_at <= now() - make_interval(secs => :age))) AS stale,
                       (SELECT count(*) FROM trips t WHERE t.zone = z.name AND t.status IN ('REQUESTED','OFFERED')) AS waiting_trips
                FROM zones z LEFT JOIN drivers d ON d.zone = z.name
                GROUP BY z.name ORDER BY z.name""",params,
                (rs,i)->new Supply(rs.getString("zone"),rs.getLong("available"),rs.getLong("offered"),rs.getLong("on_trip"),
                        rs.getLong("stale"),rs.getLong("waiting_trips")));
        return new SupplySnapshot(Instant.now(),positionSeconds,zones);
    }

    record Window(OffsetDateTime from, OffsetDateTime to) {
        MapSqlParameterSource params() { return new MapSqlParameterSource("from",from).addValue("to",to); }
    }
    /** Defaults to the last 24 hours. A window ending in the future is cut at now, so no empty future buckets. */
    static Window window(String from, String to) {
        OffsetDateTime now=OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime end=to==null ? now : time(to,"to");
        if (end.isAfter(now)) end=now;
        OffsetDateTime start=from==null ? end.minusHours(24) : time(from,"from");
        if (!start.isBefore(end)) throw Errors.badRequest("invalid_request","from must be before to");
        if (Duration.between(start,end).compareTo(MAX_WINDOW)>0) throw Errors.badRequest("invalid_request","The window can be at most 7 days");
        return new Window(start,end);
    }
    private static OffsetDateTime time(String value, String field) {
        try { return OffsetDateTime.parse(value).withOffsetSameInstant(ZoneOffset.UTC); }
        catch (DateTimeParseException e) { throw Errors.badRequest("invalid_request",field+" must be an ISO-8601 time with an offset"); }
    }
    private String knownZone(String zone) {
        if (zone==null) return null;
        Integer found=db.queryForObject("SELECT count(*) FROM zones WHERE name = :zone",new MapSqlParameterSource("zone",zone),Integer.class);
        if (found==null || found==0) throw Errors.badRequest("unknown_zone","Unknown zone");
        return zone;
    }
    private static Double number(ResultSet rs, String column) throws SQLException {
        BigDecimal value=rs.getBigDecimal(column);
        return value==null ? null : value.doubleValue();
    }
}
