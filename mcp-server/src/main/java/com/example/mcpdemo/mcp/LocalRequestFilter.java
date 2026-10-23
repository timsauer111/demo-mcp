package com.example.mcpdemo.mcp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Loopback transport only; reject browser origins and Host-based DNS rebinding. */
@Component
class LocalRequestFilter extends OncePerRequestFilter {
    private static final Set<String> HOSTS = Set.of("localhost", "127.0.0.1");
    private static final Set<String> ORIGINS = Set.of("http://localhost:8082", "http://127.0.0.1:8082");
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
        throws IOException, ServletException {
        if (!HOSTS.contains(req.getServerName())) { res.setStatus(400); return; }
        String origin = req.getHeader("Origin");
        if (origin != null && !ORIGINS.contains(origin)) { res.setStatus(403); return; }
        chain.doFilter(req, res);
    }
}
