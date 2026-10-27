package com.example.mcpdemo.mcp;

import java.net.URI;
import java.util.Locale;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** One configured identity for JWT audiences, discovery and transport validation. */
@Component
class McpEndpoint {
    private final String resource;
    private final String origin;
    private final Set<String> hosts;
    private final Set<String> origins;

    McpEndpoint(@Value("${demo.resource:http://localhost:8082/mcp}") String resource) {
        URI uri = URI.create(resource);
        String host = uri.getHost();
        boolean loopback = "localhost".equals(host) || "127.0.0.1".equals(host);
        if (host == null || !("https".equals(uri.getScheme()) || ("http".equals(uri.getScheme()) && loopback))
            || !"/mcp".equals(uri.getRawPath()) || uri.getRawUserInfo() != null
            || uri.getRawQuery() != null || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("MCP resource must be an HTTPS URL ending in /mcp (HTTP only on loopback)");
        }
        this.resource = resource;
        this.origin = uri.getScheme() + "://" + uri.getRawAuthority();
        this.hosts = loopback ? Set.of("localhost", "127.0.0.1") : Set.of(host.toLowerCase(Locale.ROOT));
        this.origins = loopback ? Set.copyOf(List.of("http://localhost:8082", "http://127.0.0.1:8082", origin)) : Set.of(origin);
    }

    String resource() { return resource; }
    String metadata() { return origin + "/.well-known/oauth-protected-resource/mcp"; }
    String challenge() { return "Bearer resource_metadata=\"" + metadata() + "\", scope=\"mcp.access\""; }
    boolean acceptsHost(String host) { return hosts.contains(host.toLowerCase(Locale.ROOT)); }
    boolean acceptsOrigin(String value) { return value == null || origins.contains(value); }
}
