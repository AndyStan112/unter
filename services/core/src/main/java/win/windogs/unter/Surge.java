package win.windogs.unter;

import java.math.BigDecimal;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

/** What applies right now: at most one surge rule and one incentive per zone, the newest active one. */
@RestController
public class Surge {
    private final JdbcTemplate db;
    public Surge(JdbcTemplate db) { this.db=db; }

    public record SurgeRule(UUID id, String zone, BigDecimal multiplier, Instant startsAt, Instant endsAt, UUID proposalId) {}
    public record Incentive(UUID id, String zone, BigDecimal bonusPerTrip, Instant startsAt, Instant endsAt, UUID proposalId) {}
    public record SurgeEvent(SurgeRule surgeRule) {}
    public record IncentiveEvent(Incentive incentive) {}

    static SurgeRule mapSurge(ResultSet rs, int row) throws SQLException {
        return new SurgeRule(rs.getObject("id",UUID.class),rs.getString("zone"),rs.getBigDecimal("multiplier"),
                Rows.time(rs,"starts_at"),Rows.time(rs,"ends_at"),rs.getObject("proposal_id",UUID.class));
    }
    static Incentive mapIncentive(ResultSet rs, int row) throws SQLException {
        return new Incentive(rs.getObject("id",UUID.class),rs.getString("zone"),rs.getBigDecimal("bonus_per_trip"),
                Rows.time(rs,"starts_at"),Rows.time(rs,"ends_at"),rs.getObject("proposal_id",UUID.class));
    }
    static final String ACTIVE="WHERE starts_at <= now() AND ends_at > now() ORDER BY zone, created_at DESC";

    @GetMapping("/surge") public List<SurgeRule> surge() {
        return db.query("SELECT DISTINCT ON (zone) * FROM surge_rules "+ACTIVE,Surge::mapSurge);
    }
    @GetMapping("/incentives") public List<Incentive> incentives() {
        return db.query("SELECT DISTINCT ON (zone) * FROM driver_incentives "+ACTIVE,Surge::mapIncentive);
    }
}
