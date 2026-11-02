package win.windogs.unter;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Records an event in the caller's transaction; Events publishes it once that commits. */
@Component
public class Outbox {
    private final JdbcTemplate db;
    private final ObjectMapper json;
    public Outbox(JdbcTemplate db, ObjectMapper json) { this.db=db; this.json=json; }
    public void add(String kind, Object data) {
        try {
            db.update("INSERT INTO outbox(id,kind,payload) VALUES (?,?,?::jsonb)",UUID.randomUUID(),kind,json.writeValueAsString(data));
        } catch (JsonProcessingException e) { throw new IllegalStateException("Event is not serializable",e); }
    }
}
