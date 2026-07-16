package com.agentic.lab.springai.service;

public class RateLimitExceededException extends RuntimeException {

    private final int maxRequests;
    private final long windowSeconds;

    public RateLimitExceededException(int maxRequests, long windowSeconds) {
        super("Rate limit exceeded: max " + maxRequests + " requests per " + windowSeconds + "s");
        this.maxRequests = maxRequests;
        this.windowSeconds = windowSeconds;
    }

    public int getMaxRequests() {
        return maxRequests;
    }

    public long getWindowSeconds() {
        return windowSeconds;
    }
}
