package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import win.windogs.unter.Zones.*;

@RestController
public class Drivers {
    static final Set<String> STATUSES=Set.of("OFFLINE","AVAILABLE","OFFERED","ON_TRIP");
    private final JdbcTemplate db;
    private final Outbox outbox;
    private final Zones zones;
    private final Dispatch dispatch;
    public Drivers(JdbcTemplate db, Outbox outbox, Zones zones, Dispatch dispatch) { this.db=db; this.outbox=outbox; this.zones=zones; this.dispatch=dispatch; }

    public record Driver(UUID id, String name, String status, UUID currentTripId, Position position, Instant positionUpdatedAt, String zone) {}
    public record StatusEvent(Driver driver, String previousStatus) {}
    public record ZoneEvent(Driver driver, String previousZone) {}
    public record NewDriver(@NotBlank @Size(max=80) String name) {}

    static Driver map(ResultSet rs, int row) throws SQLException {
        Double lat=rs.getObject("lat",Double.class), lon=rs.getObject("lon",Double.class);
        return new Driver(rs.getObject("id",UUID.class),rs.getString("name"),rs.getString("status"),rs.getObject("current_trip_id",UUID.class),
                lat==null ? null : new Position(lat,lon),Rows.time(rs,"position_updated_at"),rs.getString("zone"));
    }
    static Driver load(JdbcTemplate db, UUID id) {
        return db.query("SELECT * FROM drivers WHERE id=?",Drivers::map,id).stream().findFirst().orElseThrow(()->Errors.notFound("Driver"));
    }

    @PostMapping("/drivers") @ResponseStatus(HttpStatus.CREATED) @Transactional
    public Driver create(@Valid @RequestBody NewDriver driver) {
        UUID id=UUID.randomUUID();
        db.update("INSERT INTO drivers(id,name) VALUES (?,?)",id,driver.name());
        Driver created=load(db,id);
        outbox.add("driver.created",new StatusEvent(created,null));
        return created;
    }
    @GetMapping("/drivers") public List<Driver> list(@RequestParam(required=false) String status) {
        if (status==null) return db.query("SELECT * FROM drivers ORDER BY name",Drivers::map);
        if (!STATUSES.contains(status)) throw Errors.badRequest("invalid_request","Unknown driver status");
        return db.query("SELECT * FROM drivers WHERE status=? ORDER BY name",Drivers::map,status);
    }
    @GetMapping("/drivers/{id}") public Driver get(@PathVariable UUID id) { return load(db,id); }

    /** Going online when already online (or busy with a trip) changes nothing. */
    @PostMapping("/drivers/{id}/online") @Transactional
    public Driver online(@PathVariable UUID id) {
        if (db.update("UPDATE drivers SET status='AVAILABLE', updated_at=now() WHERE id=? AND status='OFFLINE'",id)==0) return load(db,id);
        return changed(id,"OFFLINE");
    }
    /** A pending offer is handed back first; a driver in the middle of a trip can't go offline. */
    @PostMapping("/drivers/{id}/offline") @Transactional
    public Driver offline(@PathVariable UUID id) {
        if (load(db,id).status().equals("OFFERED") && dispatch.releaseDriver(id)) return load(db,id);
        if (db.update("UPDATE drivers SET status='OFFLINE', updated_at=now() WHERE id=? AND status='AVAILABLE'",id)==1) return changed(id,"AVAILABLE");
        Driver current=load(db,id);
        if (current.status().equals("OFFLINE")) return current;
        throw Errors.conflict("driver_busy","Driver is "+current.status());
    }
    private Driver changed(UUID id, String previous) {
        Driver driver=load(db,id);
        outbox.add("driver.status_changed",new StatusEvent(driver,previous));
        return driver;
    }

    @PostMapping("/drivers/{id}/location") @ResponseStatus(HttpStatus.NO_CONTENT) @Transactional
    public void location(@PathVariable UUID id, @Valid @RequestBody Point location) {
        String zone=zones.nearest(location.lat(),location.lon());
        // Lock the row while reading the old zone, so concurrent pings can't both miss a zone change.
        List<String> previous=db.query("""
                UPDATE drivers d SET lat=?, lon=?, position_updated_at=now(), zone=?
                FROM (SELECT id, zone AS old_zone FROM drivers WHERE id=? FOR UPDATE) o
                WHERE d.id=o.id RETURNING o.old_zone""",(rs,i)->rs.getString("old_zone"),location.lat(),location.lon(),zone,id);
        if (previous.isEmpty()) throw Errors.notFound("Driver");
        // Pings are frequent; only a zone change is worth an event.
        if (!zone.equals(previous.get(0))) outbox.add("driver.zone_changed",new ZoneEvent(load(db,id),previous.get(0)));
    }
}
