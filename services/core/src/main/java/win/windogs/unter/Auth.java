package win.windogs.unter;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class Auth extends OncePerRequestFilter {
    private final byte[] expected;
    public Auth() {
        String user = System.getenv("SERVICE_USERNAME"), password = System.getenv("SERVICE_PASSWORD");
        if (user == null || password == null || user.isBlank() || password.isBlank())
            throw new IllegalStateException("Missing service authentication configuration");
        expected = ("Basic " + Base64.getEncoder().encodeToString((user + ":" + password).getBytes(StandardCharsets.UTF_8))).getBytes(StandardCharsets.UTF_8);
    }
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
        if (req.getRequestURI().equals("/healthz") && req.getMethod().equals("GET")) {
            chain.doFilter(req,res); return;
        }
        String header = req.getHeader("Authorization");
        if (header == null || !MessageDigest.isEqual(expected, header.getBytes(StandardCharsets.UTF_8))) {
            res.setStatus(401); res.setHeader("WWW-Authenticate", "Basic realm=\"Unter service\""); return;
        }
        res.setHeader("Cache-Control", "no-store");
        chain.doFilter(req,res);
    }
}
