package com.example.mcpdemo.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.URI;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@Validated
class TicketsController {
    private final TicketStore store;
    TicketsController(TicketStore store) { this.store = store; }
    record Create(@NotBlank @Size(max = 120) String title, @NotNull @Size(max = 2000) String description,
                  @NotNull TicketStore.Status status) {}
    record Patch(@Size(min = 1, max = 120) @Pattern(regexp = "(?s).*\\S.*") String title,
                 @Size(max = 2000) String description, TicketStore.Status status) {}

    @GetMapping("/health") Map<String, String> health() { return Map.of("status", "UP"); }
    @GetMapping("/tickets") TicketStore.Page list(@RequestParam(required = false) TicketStore.Status status,
        @RequestParam(defaultValue = "0") @Min(0) int offset,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        return store.list(status, offset, limit);
    }
    @GetMapping("/tickets/{id}") TicketStore.Ticket get(@PathVariable @Min(1) long id) { return store.get(id); }
    @PostMapping("/tickets") ResponseEntity<TicketStore.Ticket> create(@RequestBody @Valid Create input) {
        var ticket = store.create(input);
        return ResponseEntity.created(URI.create("/tickets/" + ticket.id())).body(ticket);
    }
    @PatchMapping("/tickets/{id}") TicketStore.Ticket patch(@PathVariable @Min(1) long id,
        @RequestBody @Valid Patch input) { return store.patch(id, input); }
    @DeleteMapping("/tickets/{id}") ResponseEntity<Void> delete(@PathVariable @Min(1) long id) {
        store.delete(id); return ResponseEntity.noContent().build();
    }
    @PostMapping("/demo/reset") ResponseEntity<Void> reset() {
        store.reset(); return ResponseEntity.noContent().build();
    }
}
