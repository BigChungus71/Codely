// Static Spring Boot fixture only. Never compile or execute.
package com.example.orders;

import java.sql.Statement;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public String findByStatus(String status) {
        Statement stmt = null;
        try {
            stmt.executeQuery("SELECT id FROM orders WHERE status = " + status);
        } catch (Exception ignored) {
        }
        return status;
    }
}
