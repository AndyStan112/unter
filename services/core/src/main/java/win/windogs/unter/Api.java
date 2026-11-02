package win.windogs.unter;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class Api {
    private final JdbcTemplate db;
    public Api(JdbcTemplate db) { this.db=db; }
    @GetMapping("/healthz") public Map<String,String> health() {
        db.queryForObject("SELECT 1",Integer.class); return Map.of("status","ok");
    }
    /** Demo numbers, kept until the stats worker computes real ones. */
    @GetMapping("/observations") public List<Map<String,Object>> observations() {
        return db.queryForList("SELECT * FROM observations ORDER BY zone");
    }
}
