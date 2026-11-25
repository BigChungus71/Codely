package example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/agents")
class Controller {
    private final AgentService service;
    Controller(AgentService service) { this.service = service; }
}
