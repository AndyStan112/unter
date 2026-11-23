package win.windogs.unter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import org.springframework.web.bind.annotation.*;
import win.windogs.unter.Zones.*;

@RestController
public class RidePlanning {
    private final Routing routing;
    private final Pricing pricing;
    private final Zones zones;
    public RidePlanning(Routing routing, Pricing pricing, Zones zones) { this.routing=routing; this.pricing=pricing; this.zones=zones; }
    public record Journey(@NotNull @Valid Point pickup, @NotNull @Valid Point dropoff) {}
    public record Estimate(Routing.Route route, BigDecimal fare, BigDecimal surgeMultiplier, String currency, String paymentMode) {}
    @PostMapping("/ride-plan")
    public Estimate plan(@Valid @RequestBody Journey journey) {
        var start=new Position(journey.pickup().lat(),journey.pickup().lon());
        var end=new Position(journey.dropoff().lat(),journey.dropoff().lon());
        var route=routing.route(start,end);
        BigDecimal surge=pricing.surge(zones.nearest(start.lat(),start.lon()));
        return new Estimate(route,pricing.price(route.distanceMeters(),surge),surge,"RON","mock");
    }
}
