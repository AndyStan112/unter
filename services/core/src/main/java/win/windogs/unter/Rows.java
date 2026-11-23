package win.windogs.unter;

import java.sql.*;
import java.time.*;

final class Rows {
    private Rows() {}
    static Instant time(ResultSet rs, String column) throws SQLException {
        OffsetDateTime value=rs.getObject(column,OffsetDateTime.class);
        return value==null ? null : value.toInstant();
    }
    static Double decimalDouble(ResultSet rs, String column) throws SQLException {
        var value=rs.getBigDecimal(column);
        return value==null ? null : value.doubleValue();
    }
}
