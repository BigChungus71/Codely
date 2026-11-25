// Static Spring Boot fixture only. Never compile or execute.
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnrelatedHealthController {
    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
