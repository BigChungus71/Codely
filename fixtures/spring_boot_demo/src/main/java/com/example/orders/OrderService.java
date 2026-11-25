// Static Spring Boot fixture only. Never compile or execute.
package com.example.orders;

import org.springframework.stereotype.Service;
import com.example.orders.OrderRepository;

@Service
public class OrderService {
    private final OrderRepository repository = new OrderRepository();

    public String fetchOrders(String filter) {
        return repository.findByStatus(filter);
    }
}
