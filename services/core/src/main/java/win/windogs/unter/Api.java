package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import com.fasterxml.jackson.databind.ObjectMapper;

@RestController
public class Api {
    private final JdbcTemplate db;
    private final ObjectMapper json;
    public Api(JdbcTemplate db, ObjectMapper json) { this.db=db; this.json=json; }
    @GetMapping("/healthz") public Map<String,String> health() {
        db.queryForObject("SELECT 1",Integer.class); return Map.of("status","ok");
    }
    @GetMapping("/observations") public List<Map<String,Object>> observations() {
        return db.queryForList("SELECT * FROM observations ORDER BY zone");
    }
    @GetMapping("/proposals") public List<Map<String,Object>> proposals() {
        return db.queryForList("SELECT * FROM proposals ORDER BY created_at DESC LIMIT 50");
    }
    public record Proposal(@NotBlank @Size(max=80) String zone, @NotBlank @Size(max=1000) String reason) {}
    @PostMapping("/proposals") @Transactional
    public Map<String,Object> create(@Valid @RequestBody Proposal proposal) throws Exception {
        if (db.queryForObject("SELECT count(*) FROM observations WHERE zone=?",Integer.class,proposal.zone()) == 0)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Unknown zone");
        UUID id=UUID.randomUUID();
        db.update("INSERT INTO proposals(id,zone,reason) VALUES (?,?,?)",id,proposal.zone(),proposal.reason());
        Map<String,Object> result=Map.of("id",id,"zone",proposal.zone(),"reason",proposal.reason(),"status","pending");
        db.update("INSERT INTO outbox(id,kind,payload) VALUES (?,'proposal.created',?::jsonb)",UUID.randomUUID(),json.writeValueAsString(result));
        return result;
    }
    public record Decision(@Pattern(regexp="approved|rejected") @NotNull String status) {}
    @PatchMapping("/proposals/{id}") @Transactional
    public Map<String,String> decide(@PathVariable UUID id, @Valid @RequestBody Decision decision) {
        int changed=db.update("UPDATE proposals SET status=? WHERE id=? AND status='pending'",decision.status(),id);
        if (changed==0) throw new ResponseStatusException(HttpStatus.CONFLICT,"No pending proposal");
        return Map.of("status",decision.status());
    }
}
