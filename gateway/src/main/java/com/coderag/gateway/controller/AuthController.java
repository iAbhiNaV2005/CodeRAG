package com.coderag.gateway.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.coderag.gateway.util.JwtUtil;

/**
 * Authentication controller.
 *
 * Provides token generation for development/testing.
 * In production, this would integrate with OAuth2 / SSO provider.
 */
@RestController
@RequestMapping("/auth")
public class AuthController {

    private final JwtUtil jwtUtil;

    public AuthController(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    /**
     * Generate a JWT token for a given user ID.
     *
     * POST /auth/token
     * Body: { "user_id": "alice" }
     * Response: { "token": "eyJ...", "user_id": "alice" }
     */
    @PostMapping("/token")
    public Map<String, String> generateToken(@RequestBody Map<String, String> request) {
        String userId = request.getOrDefault("user_id", "anonymous");

        if (userId.isBlank()) {
            userId = "anonymous";
        }

        String token = jwtUtil.generateToken(userId);

        return Map.of(
                "token", token,
                "user_id", userId,
                "expires_in", "86400"
        );
    }
}
