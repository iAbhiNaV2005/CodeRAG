package com.coderag.gateway.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Map;

/**
 * Proxy controller that forwards requests to the downstream FastAPI service.
 *
 * Key design:
 * - POST /ingest     -> FastAPI POST /ingest (JSON proxy)
 * - GET  /ingest/... -> FastAPI GET  /ingest/... (JSON proxy)
 * - POST /chat       -> FastAPI POST /chat (SSE streaming proxy)
 * - GET  /health     -> FastAPI GET  /health (JSON proxy)
 *
 * Propagates downstream HTTP status codes (e.g., 400 Bad Request, 404 Not Found)
 * instead of letting WebClientResponseException escape as 500 Internal Server Error.
 */
@RestController
public class ProxyController {

    private static final Logger log = LoggerFactory.getLogger(ProxyController.class);

    private final WebClient webClient;

    public ProxyController(@Value("${gateway.fastapi.base-url}") String baseUrl) {
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .build();
    }

    // ── Health check proxy ──────────────────────────────────────

    @GetMapping("/health")
    public Mono<Map<String, Object>> health() {
        return webClient.get()
                .uri("/health")
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .map(body -> {
                    body.put("gateway", "ok");
                    return body;
                })
                .onErrorReturn(Map.of(
                        "status", "degraded",
                        "gateway", "ok",
                        "fastapi", "unreachable"
                ));
    }

    // ── Ingest proxy ────────────────────────────────────────────

    @PostMapping("/ingest")
    public Mono<ResponseEntity<Map<String, Object>>> ingestRepo(
            @RequestBody Map<String, Object> body,
            ServerWebExchange exchange
    ) {
        log.info("Proxying POST /ingest for repo: {}", body.get("repo_url"));

        return webClient.post()
                .uri("/ingest")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .toEntity(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(WebClientResponseException.class, ex -> {
                    log.warn("Downstream error on POST /ingest: {} - {}", ex.getStatusCode(), ex.getResponseBodyAsString());
                    try {
                        Map<String, Object> errorBody = ex.getResponseBodyAs(new ParameterizedTypeReference<Map<String, Object>>() {});
                        return Mono.just(ResponseEntity.status(ex.getStatusCode()).body(errorBody));
                    } catch (Exception e) {
                        return Mono.just(ResponseEntity.status(ex.getStatusCode())
                                .body(Map.of("detail", ex.getResponseBodyAsString())));
                    }
                });
    }

    @GetMapping("/ingest/status/{repoId}")
    public Mono<ResponseEntity<Map<String, Object>>> ingestStatus(@PathVariable String repoId) {
        log.info("Proxying GET /ingest/status/{}", repoId);

        return webClient.get()
                .uri("/ingest/status/{repoId}", repoId)
                .retrieve()
                .toEntity(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(WebClientResponseException.class, ex -> {
                    log.warn("Downstream error on GET /ingest/status/{}: {} - {}", repoId, ex.getStatusCode(), ex.getResponseBodyAsString());
                    try {
                        Map<String, Object> errorBody = ex.getResponseBodyAs(new ParameterizedTypeReference<Map<String, Object>>() {});
                        return Mono.just(ResponseEntity.status(ex.getStatusCode()).body(errorBody));
                    } catch (Exception e) {
                        return Mono.just(ResponseEntity.status(ex.getStatusCode())
                                .body(Map.of("detail", ex.getResponseBodyAsString())));
                    }
                });
    }

    // ── Chat proxy (SSE streaming passthrough) ──────────────────

    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> chat(
            @RequestBody Map<String, Object> body,
            ServerWebExchange exchange
    ) {
        // Inject user ID from JWT into the request body
        String userId = exchange.getRequest().getHeaders().getFirst("X-User-Id");
        if (userId != null) {
            body.put("user_id", userId);
        }

        log.info("Proxying POST /chat for repo: {}, user: {}", body.get("repo_id"), userId);

        return webClient.post()
                .uri("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {})
                .doOnError(e -> log.error("SSE proxy error: {}", e.getMessage()));
    }
}
