/**
 * @file evidence.c
 * @brief SHA-256 + HMAC Evidence Chain Implementation
 *
 * Tamper-evident evidence chain for crash event data. Each block contains:
 *   - Monotonic block ID
 *   - Timestamp
 *   - Evidence type and payload
 *   - SHA-256 hash of the previous block (chain link)
 *   - SHA-256 hash of the current block
 *   - HMAC-SHA256 for authentication
 *
 * The chain is stored in FRAM for crash-safe persistence. If FRAM is
 * corrupted, the chain can be verified up to the point of corruption.
 *
 * @author VISTA Firmware Team
 * @version 2.0.0
 *
 * @note SHA-256 and HMAC implementations are software-based.
 *       For production, consider hardware crypto accelerator (HASH peripheral).
 */

#include "firmware.h"
#include <string.h>

/* ========================================================================== */
/*  HMAC KEY (in production, provisioned during manufacturing)                 */
/* ========================================================================== */

/** @brief Static HMAC key — placeholder for production HSM-provisioned key */
static const uint8_t g_hmac_key[EVIDENCE_HMAC_KEY_SIZE] = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F
};

/* ========================================================================== */
/*  SHA-256 SOFTWARE IMPLEMENTATION                                           */
/* ========================================================================== */

/** @brief SHA-256 round constants */
static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

/** @brief SHA-256 context */
typedef struct {
    uint32_t h[8];          /* Hash state */
    uint64_t bit_count;     /* Total bits processed */
    uint8_t buffer[64];     /* Partial block buffer */
    uint32_t buffer_len;    /* Bytes in buffer */
} sha256_ctx_t;

/**
 * @brief SHA-256 right rotation.
 */
static inline uint32_t rotr(uint32_t x, uint8_t n)
{
    return (x >> n) | (x << (32U - n));
}

/**
 * @brief SHA-256 compress function (process one 512-bit block).
 */
static void sha256_compress(sha256_ctx_t *ctx, const uint8_t block[64])
{
    uint32_t w[64];
    uint32_t a, b, c, d, e, f, g, h;

    /* Prepare message schedule */
    for (uint8_t i = 0U; i < 16U; i++) {
        w[i] = ((uint32_t)block[i * 4U] << 24U) |
               ((uint32_t)block[i * 4U + 1U] << 16U) |
               ((uint32_t)block[i * 4U + 2U] << 8U) |
               ((uint32_t)block[i * 4U + 3U]);
    }
    for (uint8_t i = 16U; i < 64U; i++) {
        uint32_t s0 = rotr(w[i - 15U], 7U) ^ rotr(w[i - 15U], 18U) ^
                       (w[i - 15U] >> 3U);
        uint32_t s1 = rotr(w[i - 2U], 17U) ^ rotr(w[i - 2U], 19U) ^
                       (w[i - 2U] >> 10U);
        w[i] = w[i - 16U] + s0 + w[i - 7U] + s1;
    }

    /* Initialize working variables */
    a = ctx->h[0]; b = ctx->h[1];
    c = ctx->h[2]; d = ctx->h[3];
    e = ctx->h[4]; f = ctx->h[5];
    g = ctx->h[6]; h = ctx->h[7];

    /* Compression function */
    for (uint8_t i = 0U; i < 64U; i++) {
        uint32_t S1 = rotr(e, 6U) ^ rotr(e, 11U) ^ rotr(e, 25U);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t temp1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a, 2U) ^ rotr(a, 13U) ^ rotr(a, 22U);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = S0 + maj;

        h = g; g = f; f = e;
        e = d + temp1;
        d = c; c = b; b = a;
        a = temp1 + temp2;
    }

    /* Add compressed chunk to hash value */
    ctx->h[0] += a; ctx->h[1] += b;
    ctx->h[2] += c; ctx->h[3] += d;
    ctx->h[4] += e; ctx->h[5] += f;
    ctx->h[6] += g; ctx->h[7] += h;
}

/**
 * @brief Initialize SHA-256 context.
 */
static void sha256_init(sha256_ctx_t *ctx)
{
    ctx->h[0] = 0x6a09e667UL;
    ctx->h[1] = 0xbb67ae85UL;
    ctx->h[2] = 0x3c6ef372UL;
    ctx->h[3] = 0xa54ff53aUL;
    ctx->h[4] = 0x510e527fUL;
    ctx->h[5] = 0x9b05688cUL;
    ctx->h[6] = 0x1f83d9abUL;
    ctx->h[7] = 0x5be0cd19UL;
    ctx->bit_count = 0ULL;
    ctx->buffer_len = 0U;
}

/**
 * @brief Update SHA-256 with data.
 */
static void sha256_update(sha256_ctx_t *ctx, const uint8_t *data, uint32_t len)
{
    for (uint32_t i = 0U; i < len; i++) {
        ctx->buffer[ctx->buffer_len] = data[i];
        ctx->buffer_len++;
        ctx->bit_count += 8ULL;

        if (ctx->buffer_len == 64U) {
            sha256_compress(ctx, ctx->buffer);
            ctx->buffer_len = 0U;
        }
    }
}

/**
 * @brief Finalize SHA-256 and produce digest.
 */
static void sha256_final(sha256_ctx_t *ctx, uint8_t digest[32])
{
    /* Pad the message */
    uint64_t total_bits = ctx->bit_count;
    ctx->buffer[ctx->buffer_len] = 0x80U;
    ctx->buffer_len++;

    if (ctx->buffer_len > 56U) {
        while (ctx->buffer_len < 64U) {
            ctx->buffer[ctx->buffer_len] = 0x00U;
            ctx->buffer_len++;
        }
        sha256_compress(ctx, ctx->buffer);
        ctx->buffer_len = 0U;
    }

    while (ctx->buffer_len < 56U) {
        ctx->buffer[ctx->buffer_len] = 0x00U;
        ctx->buffer_len++;
    }

    /* Append length in bits (big-endian) */
    for (uint8_t i = 0U; i < 8U; i++) {
        ctx->buffer[56U + i] =
            (uint8_t)(total_bits >> (56U - (i * 8U)));
    }
    sha256_compress(ctx, ctx->buffer);

    /* Produce digest */
    for (uint8_t i = 0U; i < 8U; i++) {
        digest[i * 4U]     = (uint8_t)(ctx->h[i] >> 24U);
        digest[i * 4U + 1U] = (uint8_t)(ctx->h[i] >> 16U);
        digest[i * 4U + 2U] = (uint8_t)(ctx->h[i] >> 8U);
        digest[i * 4U + 3U] = (uint8_t)(ctx->h[i]);
    }
}

/* ========================================================================== */
/*  HMAC-SHA256                                                               */
/* ========================================================================== */

/**
 * @brief Compute HMAC-SHA256.
 */
void crypto_hmac_sha256(const uint8_t *key, uint32_t key_len,
                        const uint8_t *data, uint32_t data_len,
                        uint8_t mac[32])
{
    sha256_ctx_t ctx;
    uint8_t k_pad[64];
    uint8_t o_pad[64];
    uint8_t i_hash[32];

    /* If key > block size, hash it first */
    uint8_t k_buf[32];
    if (key_len > 64U) {
        sha256_init(&ctx);
        sha256_update(&ctx, key, key_len);
        sha256_final(&ctx, k_buf);
        key = k_buf;
        key_len = 32U;
    }

    /* Inner and outer padding */
    (void)memset(k_pad, 0x36U, 64U);
    (void)memset(o_pad, 0x5CU, 64U);

    for (uint32_t i = 0U; i < key_len; i++) {
        k_pad[i] ^= key[i];
        o_pad[i] ^= key[i];
    }

    /* Inner hash: H(K XOR ipad || message) */
    sha256_init(&ctx);
    sha256_update(&ctx, k_pad, 64U);
    sha256_update(&ctx, data, data_len);
    sha256_final(&ctx, i_hash);

    /* Outer hash: H(K XOR opad || inner_hash) */
    sha256_init(&ctx);
    sha256_update(&ctx, o_pad, 64U);
    sha256_update(&ctx, i_hash, 32U);
    sha256_final(&ctx, mac);
}

/* ========================================================================== */
/*  PUBLIC API — SHA-256                                                      */
/* ========================================================================== */

void crypto_sha256(const uint8_t *data, uint32_t len, uint8_t digest[32])
{
    sha256_ctx_t ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, digest);
}

/* ========================================================================== */
/*  EVIDENCE CHAIN                                                            */
/* ========================================================================== */

/** @brief Evidence chain state */
static struct {
    uint32_t next_block_id;             /**< Next block ID to assign */
    uint8_t last_hash[EVIDENCE_SHA256_SIZE];  /**< Hash of last block */
    bool initialized;                   /**< Chain initialized */
} g_evidence;

vista_error_t evidence_init(firmware_context_t *ctx)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    (void)memset(&g_evidence, 0, sizeof(g_evidence));

    /* Read existing chain state from FRAM */
    evidence_header_t header;
    uint32_t addr = FRAM_REGION_EVIDENCE * 4096U;  /* Base of evidence region */

    /* Try to read the last block header to determine chain state */
    vista_error_t ret = fram_read(addr, (uint8_t *)&header, sizeof(header));
    if (ret == VISTA_OK) {
        /* Validate the header */
        if (header.block_id < EVIDENCE_CHAIN_MAX_BLOCKS) {
            g_evidence.next_block_id = header.block_id + 1U;
            (void)memcpy(g_evidence.last_hash, header.block_hash,
                        EVIDENCE_SHA256_SIZE);
        } else {
            /* Chain is full or corrupted — start fresh */
            g_evidence.next_block_id = 0U;
            (void)memset(g_evidence.last_hash, 0, EVIDENCE_SHA256_SIZE);
        }
    } else {
        /* FRAM read error — initialize empty chain */
        g_evidence.next_block_id = 0U;
        (void)memset(g_evidence.last_hash, 0, EVIDENCE_SHA256_SIZE);
    }

    g_evidence.initialized = true;
    ctx->evidence_block_count = g_evidence.next_block_id;

    return VISTA_OK;
}

vista_error_t evidence_add(firmware_context_t *ctx, evidence_type_t type,
                           const uint8_t *payload, uint16_t payload_size)
{
    if ((ctx == NULL) || (payload == NULL) || (payload_size > EVIDENCE_MAX_PAYLOAD)) {
        return VISTA_ERR_RANGE;
    }

    if (!g_evidence.initialized) {
        return VISTA_ERR_STATE;
    }

    if (g_evidence.next_block_id >= EVIDENCE_CHAIN_MAX_BLOCKS) {
        return VISTA_ERR_OVERFLOW;
    }

    /* Build evidence block */
    evidence_block_t block;
    (void)memset(&block, 0, sizeof(block));

    /* Fill header */
    block.header.block_id = g_evidence.next_block_id;
    block.header.type = type;
    block.header.timestamp_us = vista_get_dwt_cycles();
    block.header.payload_size = payload_size;

    /* Link to previous block */
    (void)memcpy(block.header.prev_hash, g_evidence.last_hash,
                EVIDENCE_SHA256_SIZE);

    /* Copy payload */
    (void)memcpy(block.payload, payload, payload_size);

    /* Compute block hash: SHA-256(header fields + payload) */
    /* Hash covers: block_id + type + timestamp + payload_size + payload */
    uint8_t hash_input[4 + 4 + 4 + 2 + EVIDENCE_MAX_PAYLOAD];
    uint32_t hash_len = 4U + 4U + 4U + 2U + payload_size;

    (void)memcpy(&hash_input[0], &block.header.block_id, 4U);
    (void)memcpy(&hash_input[4], &block.header.type, 4U);
    (void)memcpy(&hash_input[8], &block.header.timestamp_us, 4U);
    (void)memcpy(&hash_input[12], &block.header.payload_size, 2U);
    (void)memcpy(&hash_input[14], payload, payload_size);

    crypto_sha256(hash_input, hash_len, block.header.block_hash);

    /* Compute HMAC: HMAC-SHA256(key, block_hash || prev_hash) */
    uint8_t hmac_input[2 * EVIDENCE_SHA256_SIZE];
    (void)memcpy(hmac_input, block.header.block_hash, EVIDENCE_SHA256_SIZE);
    (void)memcpy(&hmac_input[EVIDENCE_SHA256_SIZE], block.header.prev_hash,
                EVIDENCE_SHA256_SIZE);

    crypto_hmac_sha256(g_hmac_key, EVIDENCE_HMAC_KEY_SIZE,
                       hmac_input, sizeof(hmac_input), block.header.hmac);

    /* Write to FRAM */
    uint32_t addr = (FRAM_REGION_EVIDENCE * 4096U) +
                    (g_evidence.next_block_id *
                     (sizeof(evidence_header_t) + EVIDENCE_MAX_PAYLOAD));

    uint16_t write_size = (uint16_t)(sizeof(evidence_header_t) +
                                     payload_size);
    vista_error_t ret = fram_write(addr, (const uint8_t *)&block, write_size);

    if (ret == VISTA_OK) {
        /* Update chain state */
        (void)memcpy(g_evidence.last_hash, block.header.block_hash,
                    EVIDENCE_SHA256_SIZE);
        g_evidence.next_block_id++;
        ctx->evidence_block_count = g_evidence.next_block_id;
    }

    return ret;
}

vista_error_t evidence_verify_chain(const firmware_context_t *ctx)
{
    if (ctx == NULL) {
        return VISTA_ERR_RANGE;
    }

    if (!g_evidence.initialized) {
        return VISTA_ERR_STATE;
    }

    uint32_t base_addr = FRAM_REGION_EVIDENCE * 4096U;
    uint8_t prev_hash[EVIDENCE_SHA256_SIZE];
    (void)memset(prev_hash, 0, EVIDENCE_SHA256_SIZE);

    for (uint32_t i = 0U; i < g_evidence.next_block_id; i++) {
        evidence_block_t block;
        uint32_t addr = base_addr + (i * (sizeof(evidence_header_t) +
                         EVIDENCE_MAX_PAYLOAD));

        vista_error_t ret = fram_read(addr, (uint8_t *)&block, sizeof(block));
        if (ret != VISTA_OK) {
            return VISTA_ERR_STORAGE;
        }

        /* Verify block ID */
        if (block.header.block_id != i) {
            return VISTA_ERR_CRC;
        }

        /* Verify chain link */
        if (memcmp(block.header.prev_hash, prev_hash,
                   EVIDENCE_SHA256_SIZE) != 0) {
            return VISTA_ERR_CRC;
        }

        /* Recompute block hash */
        uint8_t hash_input[4 + 4 + 4 + 2 + EVIDENCE_MAX_PAYLOAD];
        uint32_t hash_len = 4U + 4U + 4U + 2U + block.header.payload_size;

        (void)memcpy(&hash_input[0], &block.header.block_id, 4U);
        (void)memcpy(&hash_input[4], &block.header.type, 4U);
        (void)memcpy(&hash_input[8], &block.header.timestamp_us, 4U);
        (void)memcpy(&hash_input[12], &block.header.payload_size, 2U);
        (void)memcpy(&hash_input[14], block.payload,
                     block.header.payload_size);

        uint8_t computed_hash[EVIDENCE_SHA256_SIZE];
        crypto_sha256(hash_input, hash_len, computed_hash);

        if (memcmp(block.header.block_hash, computed_hash,
                   EVIDENCE_SHA256_SIZE) != 0) {
            return VISTA_ERR_CRC;
        }

        /* Verify HMAC */
        uint8_t hmac_input[2 * EVIDENCE_SHA256_SIZE];
        (void)memcpy(hmac_input, block.header.block_hash,
                    EVIDENCE_SHA256_SIZE);
        (void)memcpy(&hmac_input[EVIDENCE_SHA256_SIZE],
                    block.header.prev_hash, EVIDENCE_SHA256_SIZE);

        uint8_t computed_mac[EVIDENCE_HMAC_SIZE];
        crypto_hmac_sha256(g_hmac_key, EVIDENCE_HMAC_KEY_SIZE,
                           hmac_input, sizeof(hmac_input), computed_mac);

        if (memcmp(block.header.hmac, computed_mac,
                   EVIDENCE_HMAC_SIZE) != 0) {
            return VISTA_ERR_CRYPTO;
        }

        /* Update for next iteration */
        (void)memcpy(prev_hash, block.header.block_hash,
                    EVIDENCE_SHA256_SIZE);
    }

    return VISTA_OK;
}
