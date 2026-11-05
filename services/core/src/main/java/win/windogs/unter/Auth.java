package win.windogs.unter;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Two logins. SERVICE (gateway) may do anything. READER (the MCP server and the agent behind it)
 * may only read: any other method is refused here, before a controller or the database is reached.
 */
@Component
public class Auth extends OncePerRequestFilter {
    private static final Set<String> READ_METHODS = Set.of("GET", "HEAD");
    private final byte[] service, reader;
    public Auth() {
        service = header("SERVICE");
        reader = header("READER");
        if (MessageDigest.isEqual(service, reader))
            throw new IllegalStateException("READER and SERVICE credentials must differ");
    }
    private static byte[] header(String kind) {
        String user = System.getenv(kind + "_USERNAME"), password = System.getenv(kind + "_PASSWORD");
        if (user == null || password == null || user.isBlank() || password.isBlank())
            throw new IllegalStateException("Missing " + kind.toLowerCase() + " authentication configuration");
        return ("Basic " + Base64.getEncoder().encodeToString((user + ":" + password).getBytes(StandardCharsets.UTF_8))).getBytes(StandardCharsets.UTF_8);
    }
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
        if (req.getRequestURI().equals("/healthz") && req.getMethod().equals("GET")) {
            chain.doFilter(req,res); return;
        }
        String value = req.getHeader("Authorization");
        byte[] supplied = value == null ? new byte[0] : value.getBytes(StandardCharsets.UTF_8);
        boolean isService = MessageDigest.isEqual(service, supplied), isReader = MessageDigest.isEqual(reader, supplied);
        if (!isService && !isReader) {
            res.setStatus(401); res.setHeader("WWW-Authenticate", "Basic realm=\"Unter service\""); return;
        }
        res.setHeader("Cache-Control", "no-store");
        if (isReader && !READ_METHODS.contains(req.getMethod())) {
            res.setStatus(403); res.setContentType("application/json");
            res.getWriter().write("{\"error\":\"read_only\",\"message\":\"This login can only read\"}");
            return;
        }
        chain.doFilter(req,res);
    }
}
