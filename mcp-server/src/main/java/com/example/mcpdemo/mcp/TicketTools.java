package com.example.mcpdemo.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.modelcontextprotocol.common.McpTransportContext;
import io.modelcontextprotocol.spec.McpSchema;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
class TicketTools {
    static final String SUBJECT_KEY = "authenticated-subject";
    private final TokenExchange exchange;
    private final RestClient api;
    private final ObjectMapper mapper;
    TicketTools(TokenExchange exchange, @Value("${demo.api-base}") String base, ObjectMapper mapper) {
        this.exchange = exchange;
        this.api = TokenExchange.http().baseUrl(base).build();
        this.mapper = mapper;
    }
    record Ticket(long id, String title, String description, String status) {}
    record Page(List<Ticket> tickets, int offset, int limit, int total) {}

    McpSchema.CallToolResult list(McpTransportContext ctx, McpSchema.CallToolRequest req) {
        return safe(() -> {
            var args = req.arguments() == null ? Map.<String,Object>of() : req.arguments();
            allowed(args, Set.of("status", "offset", "limit"));
            int offset = (int) integer(args.getOrDefault("offset", 0), 0, Integer.MAX_VALUE);
            int limit = (int) integer(args.getOrDefault("limit", 20), 1, 100);
            Object status = args.get("status");
            if (status != null && !Set.of("OPEN", "IN_PROGRESS", "CLOSED").contains(status))
                throw new IllegalArgumentException();
            String token = exchange.exchange(subject(ctx));
            var page = api.get().uri(b -> {
                b.path("/tickets").queryParam("offset", offset).queryParam("limit", limit);
                if (status != null) b.queryParam("status", status);
                return b.build();
            }).headers(h -> h.setBearerAuth(token)).retrieve().body(Page.class);
            if (page == null) throw new IllegalStateException();
            return page;
        });
    }
    McpSchema.CallToolResult get(McpTransportContext ctx, McpSchema.CallToolRequest req) {
        return safe(() -> {
            var args = req.arguments() == null ? Map.<String,Object>of() : req.arguments();
            allowed(args, Set.of("id"));
            long id = integer(args.get("id"), 1, Long.MAX_VALUE);
            String token = exchange.exchange(subject(ctx));
            var ticket = api.get().uri("/tickets/{id}", id).headers(h -> h.setBearerAuth(token))
                .retrieve().body(Ticket.class);
            if (ticket == null) throw new IllegalStateException();
            return ticket;
        });
    }
    private TokenExchange.Subject subject(McpTransportContext ctx) {
        if (!(ctx.get(SUBJECT_KEY) instanceof TokenExchange.Subject subject)) throw new IllegalStateException();
        return subject;
    }
    static long integer(Object value, long min, long max) {
        if (!(value instanceof Number number)) throw new IllegalArgumentException();
        try {
            long n = new BigDecimal(number.toString()).longValueExact();
            if (n < min || n > max) throw new IllegalArgumentException();
            return n;
        } catch (ArithmeticException | NumberFormatException e) { throw new IllegalArgumentException(); }
    }
    private static void allowed(Map<String,Object> args, Set<String> keys) {
        if (!keys.containsAll(args.keySet())) throw new IllegalArgumentException();
    }
    private McpSchema.CallToolResult safe(Supplier<Object> operation) {
        try {
            Object data = operation.get();
            return McpSchema.CallToolResult.builder().addTextContent(mapper.writeValueAsString(data))
                .structuredContent(data).isError(false).build();
        } catch (IllegalArgumentException e) { return error("invalid_arguments"); }
        catch (RestClientResponseException e) {
            return error(e.getStatusCode().value() == 404 ? "ticket_not_found" : "backend_unavailable");
        } catch (Exception e) { return error("backend_unavailable"); }
    }
    private static McpSchema.CallToolResult error(String code) {
        // Never include exception messages, request headers, tokens or backend response bodies.
        return McpSchema.CallToolResult.builder().addTextContent(code).isError(true).build();
    }
}
