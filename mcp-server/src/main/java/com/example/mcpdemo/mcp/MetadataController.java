package com.example.mcpdemo.mcp;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MetadataController {
    private final String issuer;
    private final McpEndpoint endpoint;
    MetadataController(@Value("${demo.issuer}") String issuer, McpEndpoint endpoint) {
        this.issuer = issuer;
        this.endpoint = endpoint;
    }
    @GetMapping("/health") Map<String, String> health() { return Map.of("status", "UP"); }
    @GetMapping({"/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"})
    Map<String, Object> metadata() {
        return Map.of("resource", endpoint.resource(), "authorization_servers", List.of(issuer),
            "scopes_supported", List.of("mcp.access"), "bearer_methods_supported", List.of("header"));
    }
}
