// Static Spring Boot fixture only. Never compile or execute.
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.example.orders.OrderService;

@RestController
public class OrderController {
    private final OrderService orderService = new OrderService();

    @GetMapping("/api/orders")
    public String listOrders() {
        return orderService.fetchOrders("active");
    }
}
