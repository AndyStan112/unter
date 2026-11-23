package win.windogs.unter;

import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import com.fasterxml.jackson.databind.ObjectMapper;
import win.windogs.unter.Zones.Position;

/** Fixed provider URL, bounded timeouts and bounded cache; no caller-supplied upstream URLs. */
@Component
public class Routing {
    public record Step(String instruction, double distanceMeters, double durationSeconds, Position position) {}
    public record Route(double distanceMeters, Double durationSeconds, String source, List<Position> geometry,
                        List<Step> steps, String warning) {}
    private record Cached(long at, Route route) {}
    private final Map<String,Cached> cache=new LinkedHashMap<>();
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final ObjectMapper json;
    private final String base;
    public Routing(ObjectMapper json, @Value("${ROUTING_URL:https://router.project-osrm.org}") String base) {
        this.json=json; this.base=base.replaceAll("/+$", "");
    }
    public Route route(Position start, Position end) {
        String key=start.lon()+","+start.lat()+";"+end.lon()+","+end.lat();
        synchronized(cache) {
            Cached cached=cache.get(key);
            if (cached!=null && System.currentTimeMillis()-cached.at()<300_000) return cached.route();
        }
        Route result;
        try {
            if (base.isBlank()) throw new IllegalStateException("Routing disabled");
            var request=HttpRequest.newBuilder(URI.create(base+"/route/v1/driving/"+key+"?overview=full&geometries=geojson&steps=true"))
                .timeout(Duration.ofSeconds(5)).header("User-Agent","Unter/1.0 (https://github.com/AndyStan112/unter)").GET().build();
            var response=http.send(request,HttpResponse.BodyHandlers.ofString());
            if (response.statusCode()!=200 || response.body().length()>2_000_000) throw new IllegalStateException("Routing unavailable");
            JsonNode root=json.readTree(response.body());
            if (!root.path("code").asText().equals("Ok") || root.path("routes").isEmpty()) throw new IllegalStateException("No road route");
            JsonNode route=root.path("routes").get(0);
            double distance=route.path("distance").asDouble(-1), duration=route.path("duration").asDouble(-1);
            if (!Double.isFinite(distance) || !Double.isFinite(duration) || distance<0 || duration<0)
                throw new IllegalArgumentException("Invalid route metrics");
            List<Position> points=new ArrayList<>();
            for (JsonNode point:route.path("geometry").path("coordinates")) {
                double lat=point.get(1).asDouble(),lon=point.get(0).asDouble();
                if (!Double.isFinite(lat) || !Double.isFinite(lon) || Math.abs(lat)>90 || Math.abs(lon)>180)
                    throw new IllegalArgumentException("Invalid route coordinates");
                points.add(new Position(lat,lon));
            }
            if (points.size()<2) throw new IllegalArgumentException("Empty route");
            List<Step> steps=new ArrayList<>();
            for (JsonNode leg:route.path("legs")) for (JsonNode step:leg.path("steps")) {
                JsonNode maneuver=step.path("maneuver"), point=maneuver.path("location");
                String instruction=maneuver.path("type").asText().replace('_',' ');
                if (maneuver.has("modifier")) instruction+=" "+maneuver.path("modifier").asText();
                if (!step.path("name").asText().isBlank()) instruction+=" onto "+step.path("name").asText();
                if (maneuver.has("exit")) instruction+=" (exit "+maneuver.path("exit").asInt()+")";
                steps.add(new Step(instruction,step.path("distance").asDouble(),step.path("duration").asDouble(),new Position(point.get(1).asDouble(),point.get(0).asDouble())));
            }
            result=new Route(distance,duration,"road",points,steps,null);
        } catch (Exception error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            result=new Route(Zones.distanceKm(start.lat(),start.lon(),end.lat(),end.lon())*1000,null,"straight_line",
                    List.of(start,end),List.of(),"Road routing unavailable. Showing straight-line distance; ETA unavailable.");
        }
        synchronized(cache) {
            if (cache.size()>=256) cache.remove(cache.keySet().iterator().next());
            // Retry failed providers soon; don't cache a fallback for five minutes.
            cache.put(key,new Cached(System.currentTimeMillis()-(result.source().equals("road") ? 0 : 285_000),result));
        }
        return result;
    }
}
