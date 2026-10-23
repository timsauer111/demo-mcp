package com.example.mcpdemo.api;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
class TicketStore {
    enum Status { OPEN, IN_PROGRESS, CLOSED }
    record Ticket(long id, String title, String description, Status status) {}
    record Page(List<Ticket> tickets, int offset, int limit, int total) {}
    private final Map<Long, Ticket> tickets = new LinkedHashMap<>();
    private long nextId;
    TicketStore() { reset(); }

    synchronized void reset() {
        tickets.clear();
        tickets.put(1L, new Ticket(1, "Drucker im Demo-Büro", "Synthetisch: Papierfach prüfen.", Status.OPEN));
        tickets.put(2L, new Ticket(2, "Testzugang vorbereiten", "Synthetisch: Einweisung terminieren.", Status.IN_PROGRESS));
        tickets.put(3L, new Ticket(3, "Demo-Handbuch ergänzen", "Synthetisch: Checkliste aktualisiert.", Status.CLOSED));
        nextId = 4;
    }
    synchronized Page list(Status status, int offset, int limit) {
        var all = tickets.values().stream().filter(t -> status == null || t.status() == status).toList();
        return new Page(all.stream().skip(offset).limit(limit).toList(), offset, limit, all.size());
    }
    synchronized Ticket get(long id) {
        var ticket = tickets.get(id);
        if (ticket == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "ticket_not_found");
        return ticket;
    }
    synchronized Ticket create(TicketsController.Create input) {
        var ticket = new Ticket(nextId++, input.title(), input.description(), input.status());
        tickets.put(ticket.id(), ticket);
        return ticket;
    }
    synchronized Ticket patch(long id, TicketsController.Patch input) {
        var old = get(id);
        var ticket = new Ticket(id, input.title() == null ? old.title() : input.title(),
            input.description() == null ? old.description() : input.description(),
            input.status() == null ? old.status() : input.status());
        tickets.put(id, ticket);
        return ticket;
    }
    synchronized void delete(long id) { get(id); tickets.remove(id); }
}
