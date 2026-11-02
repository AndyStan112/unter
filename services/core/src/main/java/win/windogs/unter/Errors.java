package win.windogs.unter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** Every failure leaves core as {"error": code, "message": text}; internals are never exposed. */
@RestControllerAdvice
public class Errors {
    private static final Logger log=LoggerFactory.getLogger(Errors.class);
    public static class ApiException extends RuntimeException {
        final HttpStatus status; final String code;
        public ApiException(HttpStatus status, String code, String message) { super(message); this.status=status; this.code=code; }
    }
    public static ApiException badRequest(String code, String message) { return new ApiException(HttpStatus.BAD_REQUEST,code,message); }
    public static ApiException notFound(String what) { return new ApiException(HttpStatus.NOT_FOUND,"not_found",what+" not found"); }
    public static ApiException conflict(String code, String message) { return new ApiException(HttpStatus.CONFLICT,code,message); }

    public record Body(String error, String message) {}
    private static ResponseEntity<Body> reply(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(new Body(code,message));
    }

    @ExceptionHandler(ApiException.class) ResponseEntity<Body> api(ApiException e) { return reply(e.status,e.code,e.getMessage()); }
    @ExceptionHandler(MethodArgumentNotValidException.class) ResponseEntity<Body> invalid(MethodArgumentNotValidException e) {
        var field=e.getBindingResult().getFieldError();
        return reply(HttpStatus.BAD_REQUEST,"invalid_request",field==null ? "Invalid request" : field.getField()+": "+field.getDefaultMessage());
    }
    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class,
            HandlerMethodValidationException.class, MissingServletRequestParameterException.class})
    ResponseEntity<Body> unreadable(Exception e) { return reply(HttpStatus.BAD_REQUEST,"invalid_request","Invalid request"); }
    @ExceptionHandler(NoResourceFoundException.class) ResponseEntity<Body> missing(Exception e) { return reply(HttpStatus.NOT_FOUND,"not_found","Not found"); }
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class) ResponseEntity<Body> method(Exception e) {
        return reply(HttpStatus.METHOD_NOT_ALLOWED,"method_not_allowed","Method not allowed");
    }
    @ExceptionHandler(ResponseStatusException.class) ResponseEntity<Body> status(ResponseStatusException e) {
        HttpStatus status=HttpStatus.valueOf(e.getStatusCode().value());
        return reply(status,status.name().toLowerCase(),e.getReason()==null ? status.getReasonPhrase() : e.getReason());
    }
    @ExceptionHandler(Exception.class) ResponseEntity<Body> unexpected(Exception e) {
        // Only the type: messages can carry SQL or request data.
        log.warn("Unhandled {}",e.getClass().getSimpleName());
        return reply(HttpStatus.INTERNAL_SERVER_ERROR,"internal_error","Internal error");
    }
}
