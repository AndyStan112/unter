package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class Riders {
    private final JdbcTemplate db;
    public Riders(JdbcTemplate db) { this.db=db; }
    public record Rider(UUID id, String name, Instant createdAt) {}
    public record NewRider(@NotBlank @Size(max=80) String name) {}

    @PostMapping("/riders") @ResponseStatus(HttpStatus.CREATED)
    public Rider create(@Valid @RequestBody NewRider rider) {
        UUID id=UUID.randomUUID();
        db.update("INSERT INTO riders(id,name) VALUES (?,?)",id,rider.name());
        return get(id);
    }
    @GetMapping("/riders/{id}") public Rider get(@PathVariable UUID id) {
        return db.query("SELECT * FROM riders WHERE id=?",(rs,i)->new Rider(rs.getObject("id",UUID.class),rs.getString("name"),
                Rows.time(rs,"created_at")),id).stream().findFirst().orElseThrow(()->Errors.notFound("Rider"));
    }
}
