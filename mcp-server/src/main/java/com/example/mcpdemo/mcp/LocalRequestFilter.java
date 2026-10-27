package com.example.mcpdemo.mcp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Reject foreign browser origins and Host-based DNS rebinding, also behind the HTTPS proxy. */
@Component
class LocalRequestFilter extends OncePerRequestFilter {
    private final McpEndpoint endpoint;
    LocalRequestFilter(McpEndpoint endpoint) { this.endpoint = endpoint; }
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
        throws IOException, ServletException {
        if (!endpoint.acceptsHost(req.getServerName())) { res.setStatus(400); return; }
        String origin = req.getHeader("Origin");
        if (!endpoint.acceptsOrigin(origin)) { res.setStatus(403); return; }
        chain.doFilter(req, res);
    }
}
