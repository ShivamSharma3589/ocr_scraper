CREATE TABLE IF NOT EXISTS retailers (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    slug          VARCHAR(64)  NOT NULL UNIQUE,
    name          VARCHAR(128) NOT NULL,
    domain        VARCHAR(190) NOT NULL,
    region        CHAR(2)      NOT NULL DEFAULT 'GB',
    meta_page_id  VARCHAR(64),
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS brands (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    canonical_name VARCHAR(128) NOT NULL UNIQUE,
    match_pattern  VARCHAR(255) NOT NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS runs (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_uid        VARCHAR(32)  NOT NULL,
    platform       VARCHAR(32)  NOT NULL,
    retailer_id    INT          NOT NULL,
    region         CHAR(2)      NOT NULL,
    window_start   DATE,
    window_end     DATE,
    started_at     DATETIME     NOT NULL,
    finished_at    DATETIME,
    status         VARCHAR(16)  NOT NULL DEFAULT 'running',
    creatives_seen INT          NOT NULL DEFAULT 0,
    credits_used   INT          NOT NULL DEFAULT 0,
    stats          JSON,
    json_path      VARCHAR(512),
    error_message  TEXT,
    UNIQUE KEY uq_run (run_uid, platform, retailer_id),
    KEY ix_runs_platform_started (platform, started_at),
    CONSTRAINT fk_runs_retailer FOREIGN KEY (retailer_id) REFERENCES retailers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS advertisers (
    id                     BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform               VARCHAR(32)  NOT NULL,
    platform_advertiser_id VARCHAR(128) NOT NULL,
    name                   VARCHAR(255),
    UNIQUE KEY uq_advertiser (platform, platform_advertiser_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creatives (
    id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform             VARCHAR(32)  NOT NULL,
    platform_creative_id VARCHAR(128) NOT NULL,
    retailer_id          INT          NOT NULL,
    advertiser_id        BIGINT,
    format               VARCHAR(16),
    campaign_type        VARCHAR(16),
    first_shown          DATETIME,
    last_shown           DATETIME,
    total_days_shown     INT,
    details_url          VARCHAR(1024),
    media_url            VARCHAR(1024),
    image_path           VARCHAR(512),
    first_seen_at        DATETIME     NOT NULL,
    last_seen_at         DATETIME     NOT NULL,
    UNIQUE KEY uq_creative (platform, platform_creative_id),
    KEY ix_creatives_retailer (retailer_id, platform),
    KEY ix_creatives_lastseen (last_seen_at),
    KEY ix_creatives_type (campaign_type),
    CONSTRAINT fk_creatives_retailer FOREIGN KEY (retailer_id) REFERENCES retailers(id),
    CONSTRAINT fk_creatives_advertiser FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creative_copy (
    creative_id       BIGINT      NOT NULL PRIMARY KEY,
    extraction_source VARCHAR(16) NOT NULL,
    headline          TEXT,
    description       TEXT,
    display_url       VARCHAR(512),
    landing_url       TEXT,
    cta_text          VARCHAR(128),
    raw_text          MEDIUMTEXT,
    is_truncated      BOOLEAN     NOT NULL DEFAULT FALSE,
    extracted_at      DATETIME    NOT NULL,
    CONSTRAINT fk_copy_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creative_offers (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    creative_id   BIGINT NOT NULL,
    promo_code    VARCHAR(64),
    discount_text VARCHAR(128),
    discount_pct  DECIMAL(5,2),
    UNIQUE KEY uq_offer (creative_id, promo_code, discount_text),
    KEY ix_offers_code (promo_code),
    CONSTRAINT fk_offers_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creative_brands (
    creative_id BIGINT NOT NULL,
    brand_id    INT    NOT NULL,
    PRIMARY KEY (creative_id, brand_id),
    CONSTRAINT fk_cb_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE,
    CONSTRAINT fk_cb_brand FOREIGN KEY (brand_id) REFERENCES brands(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creative_sitelinks (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    creative_id BIGINT NOT NULL,
    title       VARCHAR(255),
    description TEXT,
    CONSTRAINT fk_sitelinks_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS creative_observations (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    creative_id BIGINT   NOT NULL,
    run_id      BIGINT   NOT NULL,
    observed_at DATETIME NOT NULL,
    UNIQUE KEY uq_observation (creative_id, run_id),
    KEY ix_obs_run (run_id),
    CONSTRAINT fk_obs_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE,
    CONSTRAINT fk_obs_run FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS meta_ad_details (
    creative_id         BIGINT PRIMARY KEY,
    page_id             VARCHAR(64),
    page_name           VARCHAR(255),
    publisher_platforms JSON,
    is_active           BOOLEAN,
    start_date          DATE,
    end_date            DATE,
    caption             VARCHAR(512),
    link_description    TEXT,
    cta_type            VARCHAR(64),
    currency            VARCHAR(8),
    CONSTRAINT fk_meta_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS google_search_ad_details (
    creative_id    BIGINT PRIMARY KEY,
    keyword        VARCHAR(255),
    position       INT,
    block_position VARCHAR(32),
    CONSTRAINT fk_gsearch_creative FOREIGN KEY (creative_id) REFERENCES creatives(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
