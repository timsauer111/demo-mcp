package com.example.mcpdemo.api;

import jakarta.validation.ConstraintViolationException;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler({ConstraintViolationException.class, MethodArgumentNotValidException.class,
        MethodArgumentTypeMismatchException.class, HttpMessageNotReadableException.class})
    ResponseEntity<?> invalid(Exception ignored) { return ResponseEntity.badRequest().body(Map.of("error", "invalid_request")); }
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<?> missing(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode()).body(Map.of("error", "ticket_not_found"));
    }
}
