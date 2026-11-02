package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.sql.*;
import java.time.*;
import java.time.format.DateTimeParseException;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import win.windogs.unter.Surge.*;

/**
 * Changes the agent (or anyone) suggests and a person approves. Approving a surge or incentive proposal
 * creates the rule in the same transaction; a proposal without a type only records the decision.
 */
@RestController
public class Proposals {
    private final JdbcTemplate db;
    private final Outbox outbox;
    private final ObjectMapper json;
    public Proposals(JdbcTemplate db, Outbox outbox, ObjectMapper json) { this.db=db; this.outbox=outbox; this.json=json; }

    public record Proposal(UUID id, String zone, String type, JsonNode params, String reason, String status, Instant createdAt, Instant decidedAt) {}
    public record ProposalEvent(Proposal proposal) {}
    public record NewProposal(@NotBlank @Size(max=80) String zone, @NotBlank @Size(max=1000) String reason,
                              @Pattern(regexp="surge|incentive") String type, JsonNode params) {}
    public record Decision(@Pattern(regexp="approved|rejected") @NotNull String status) {}

    Proposal map(ResultSet rs, int row) throws SQLException {
        String params=rs.getString("params");
        try {
            return new Proposal(rs.getObject("id",UUID.class),rs.getString("zone"),rs.getString("type"),params==null ? null : json.readTree(params),
                    rs.getString("reason"),rs.getString("status"),Rows.time(rs,"created_at"),Rows.time(rs,"decided_at"));
        } catch (JsonProcessingException e) { throw new IllegalStateException("Stored params are not JSON",e); }
    }

    @GetMapping("/proposals") public List<Proposal> proposals() {
        return db.query("SELECT * FROM proposals ORDER BY created_at DESC LIMIT 50",this::map);
    }
    @PostMapping("/proposals") @Transactional
    public Proposal create(@Valid @RequestBody NewProposal proposal) {
        if (db.queryForObject("SELECT count(*) FROM zones WHERE name=?",Integer.class,proposal.zone())==0)
            throw Errors.badRequest("unknown_zone","Unknown zone");
        ObjectNode params=params(proposal.type(),proposal.params());
        Proposal created=db.query("INSERT INTO proposals(id,zone,reason,type,params) VALUES (?,?,?,?,?::jsonb) RETURNING *",this::map,
                UUID.randomUUID(),proposal.zone(),proposal.reason(),proposal.type(),params==null ? null : params.toString()).get(0);
        // Flat, unlike the other events: consumers already read proposal.created this way.
        outbox.add("proposal.created",created);
        return created;
    }
    @PatchMapping("/proposals/{id}") @Transactional
    public Proposal decide(@PathVariable UUID id, @Valid @RequestBody Decision decision) {
        // Only one decision can win, even if two people click at the same moment.
        List<Proposal> decided=db.query("UPDATE proposals SET status=?, decided_at=now() WHERE id=? AND status='pending' RETURNING *",
                this::map,decision.status(),id);
        if (decided.isEmpty()) {
            if (db.queryForObject("SELECT count(*) FROM proposals WHERE id=?",Integer.class,id)==0) throw Errors.notFound("Proposal");
            throw Errors.conflict("proposal_not_pending","Proposal was already decided");
        }
        Proposal proposal=decided.get(0);
        outbox.add("proposal.decided",new ProposalEvent(proposal));
        if (proposal.status().equals("approved") && proposal.type()!=null) apply(proposal);
        return proposal;
    }

    private void apply(Proposal p) {
        JsonNode params=p.params();
        Timestamp starts=Timestamp.from(Instant.parse(params.get("starts_at").asText())), ends=Timestamp.from(Instant.parse(params.get("ends_at").asText()));
        if (p.type().equals("surge")) {
            SurgeRule rule=db.query("INSERT INTO surge_rules(id,zone,multiplier,starts_at,ends_at,proposal_id) VALUES (?,?,?,?,?,?) RETURNING *",Surge::mapSurge,
                    UUID.randomUUID(),p.zone(),params.get("multiplier").decimalValue(),starts,ends,p.id()).get(0);
            outbox.add("surge.changed",new SurgeEvent(rule));
        } else {
            Incentive incentive=db.query("INSERT INTO driver_incentives(id,zone,bonus_per_trip,starts_at,ends_at,proposal_id) VALUES (?,?,?,?,?,?) RETURNING *",Surge::mapIncentive,
                    UUID.randomUUID(),p.zone(),params.get("bonus_per_trip").decimalValue(),starts,ends,p.id()).get(0);
            outbox.add("incentive.changed",new IncentiveEvent(incentive));
        }
    }

    /** Checks and normalizes the parameters of a typed proposal: an amount and a time window. */
    private ObjectNode params(String type, JsonNode given) {
        boolean none=given==null || given.isNull();
        if (type==null) {
            if (!none) throw Errors.badRequest("invalid_request","params need a type");
            return null;
        }
        if (none || !given.isObject()) throw Errors.badRequest("invalid_request","params are required for a "+type+" proposal");
        Instant starts=instant(given,"starts_at"), ends=instant(given,"ends_at");
        if (!ends.isAfter(starts)) throw Errors.badRequest("invalid_request","ends_at must be after starts_at");
        if (!ends.isAfter(Instant.now())) throw Errors.badRequest("invalid_request","ends_at must be in the future");
        ObjectNode params=json.createObjectNode();
        if (type.equals("surge")) params.put("multiplier",amount(given,"multiplier",BigDecimal.ONE,new BigDecimal("3")));
        else params.put("bonus_per_trip",amount(given,"bonus_per_trip",BigDecimal.ZERO,new BigDecimal("20")));
        return params.put("starts_at",starts.toString()).put("ends_at",ends.toString());
    }
    private static Instant instant(JsonNode params, String field) {
        try { return OffsetDateTime.parse(params.path(field).asText()).toInstant(); }
        catch (DateTimeParseException e) { throw Errors.badRequest("invalid_request",field+" must be an ISO-8601 time"); }
    }
    private static BigDecimal amount(JsonNode params, String field, BigDecimal min, BigDecimal max) {
        JsonNode value=params.path(field);
        if (!value.isNumber()) throw Errors.badRequest("invalid_request",field+" must be a number");
        BigDecimal amount=value.decimalValue();
        if (amount.compareTo(min)<0 || amount.compareTo(max)>0 || amount.stripTrailingZeros().scale()>2)
            throw Errors.badRequest("invalid_request",field+" must be between "+min+" and "+max+", with at most 2 decimals");
        return amount;
    }
}
