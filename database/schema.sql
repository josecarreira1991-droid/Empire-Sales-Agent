-- ============================================
-- Empire Sales Agent - Database Schema
-- PostgreSQL 16
-- ============================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- LEADS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255),
    phone VARCHAR(20),
    email VARCHAR(255),
    address TEXT,
    city VARCHAR(100),
    county VARCHAR(50),
    zip_code VARCHAR(10),
    parcel_id VARCHAR(30),
    property_type VARCHAR(50),
    year_built INTEGER,
    square_footage INTEGER,
    bedrooms INTEGER,
    bathrooms NUMERIC(3,1),
    assessed_value NUMERIC(12,2),
    market_value NUMERIC(12,2),
    last_sale_date DATE,
    last_sale_price NUMERIC(12,2),
    homestead BOOLEAN DEFAULT false,
    source VARCHAR(50) NOT NULL DEFAULT 'manual',
    renovation_score INTEGER DEFAULT 0 CHECK (renovation_score BETWEEN 0 AND 100),
    score_reasons TEXT[],
    status VARCHAR(30) NOT NULL DEFAULT 'new',
    consent_given BOOLEAN DEFAULT false,
    consent_date TIMESTAMP,
    consent_method VARCHAR(50),
    do_not_call BOOLEAN DEFAULT false,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN (
        'new', 'contacted', 'no_answer', 'follow_up',
        'interested', 'estimate_booked', 'estimate_done',
        'proposal_sent', 'closed_won', 'closed_lost', 'do_not_call'
    )),
    CONSTRAINT valid_source CHECK (source IN (
        'pdf', 'scraper_permits', 'scraper_nal', 'scraper_gis',
        'website', 'referral', 'manual', 'social_media'
    )),
    CONSTRAINT valid_county CHECK (county IN ('Lee', 'Collier'))
);

CREATE INDEX idx_leads_phone ON leads(phone);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_score ON leads(renovation_score DESC);
CREATE INDEX idx_leads_county ON leads(county);
CREATE INDEX idx_leads_source ON leads(source);
CREATE INDEX idx_leads_do_not_call ON leads(do_not_call) WHERE do_not_call = true;

-- ============================================
-- INTERACTIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS interactions (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL DEFAULT 'outbound',
    status VARCHAR(20) NOT NULL,
    duration_seconds INTEGER,
    transcript TEXT,
    sms_content TEXT,
    notes TEXT,
    twilio_sid VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_type CHECK (type IN ('call', 'sms', 'voicemail', 'email')),
    CONSTRAINT valid_direction CHECK (direction IN ('outbound', 'inbound')),
    CONSTRAINT valid_interaction_status CHECK (status IN (
        'completed', 'no_answer', 'busy', 'failed',
        'voicemail', 'opted_out', 'delivered', 'undelivered'
    ))
);

CREATE INDEX idx_interactions_lead ON interactions(lead_id);
CREATE INDEX idx_interactions_created ON interactions(created_at);
CREATE INDEX idx_interactions_type ON interactions(type);

-- ============================================
-- FOLLOW-UPS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS follow_ups (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    scheduled_at TIMESTAMP NOT NULL,
    type VARCHAR(20) NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    message_template VARCHAR(50),
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMP,
    result VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_followup_type CHECK (type IN ('call', 'sms')),
    CONSTRAINT max_attempts CHECK (attempt_number <= 5)
);

CREATE INDEX idx_followups_scheduled ON follow_ups(scheduled_at) WHERE completed = false;
CREATE INDEX idx_followups_lead ON follow_ups(lead_id);

-- ============================================
-- SOCIAL POSTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS social_posts (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(30) NOT NULL,
    content TEXT NOT NULL,
    image_url TEXT,
    hashtags TEXT[],
    post_type VARCHAR(30),
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    scheduled_at TIMESTAMP,
    posted_at TIMESTAMP,
    platform_post_id VARCHAR(100),
    engagement_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_platform CHECK (platform IN ('instagram', 'facebook', 'google_business')),
    CONSTRAINT valid_post_status CHECK (status IN ('draft', 'scheduled', 'posted', 'failed')),
    CONSTRAINT valid_post_type CHECK (post_type IN (
        'before_after', 'tip', 'testimonial', 'offer',
        'educational', 'behind_scenes', 'project_showcase'
    ))
);

CREATE INDEX idx_posts_scheduled ON social_posts(scheduled_at) WHERE status = 'scheduled';
CREATE INDEX idx_posts_platform ON social_posts(platform);

-- ============================================
-- OPT-OUTS TABLE (CRITICAL FOR COMPLIANCE)
-- ============================================
CREATE TABLE IF NOT EXISTS opt_outs (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) UNIQUE NOT NULL,
    opted_out_at TIMESTAMP DEFAULT NOW(),
    source VARCHAR(50) NOT NULL,
    CONSTRAINT valid_optout_source CHECK (source IN (
        'sms_stop', 'call_request', 'manual', 'dnc_list'
    ))
);

CREATE INDEX idx_optouts_phone ON opt_outs(phone);

-- ============================================
-- PERMITS TABLE (from web scraping)
-- ============================================
CREATE TABLE IF NOT EXISTS permits (
    id SERIAL PRIMARY KEY,
    permit_number VARCHAR(50) UNIQUE,
    county VARCHAR(50) NOT NULL,
    permit_type VARCHAR(100),
    description TEXT,
    site_address TEXT,
    parcel_id VARCHAR(30),
    applicant_name VARCHAR(255),
    contractor_name VARCHAR(255),
    valuation NUMERIC(12,2),
    status VARCHAR(50),
    applied_date DATE,
    issued_date DATE,
    finaled_date DATE,
    scraped_at TIMESTAMP DEFAULT NOW(),
    linked_lead_id INTEGER REFERENCES leads(id),
    CONSTRAINT valid_permit_county CHECK (county IN ('Lee', 'Collier'))
);

CREATE INDEX idx_permits_parcel ON permits(parcel_id);
CREATE INDEX idx_permits_address ON permits(site_address);
CREATE INDEX idx_permits_date ON permits(applied_date DESC);

-- ============================================
-- SCRAPING RUNS TABLE (audit trail)
-- ============================================
CREATE TABLE IF NOT EXISTS scraping_runs (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    records_found INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_details TEXT,
    status VARCHAR(20) DEFAULT 'running',
    CONSTRAINT valid_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Check opt-out before interaction
CREATE OR REPLACE FUNCTION check_opt_out()
RETURNS TRIGGER AS $$
DECLARE
    lead_phone VARCHAR(20);
BEGIN
    SELECT phone INTO lead_phone FROM leads WHERE id = NEW.lead_id;
    IF EXISTS (SELECT 1 FROM opt_outs WHERE phone = lead_phone) THEN
        RAISE EXCEPTION 'Cannot contact opted-out number: %', lead_phone;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_opt_out_before_interaction
    BEFORE INSERT ON interactions
    FOR EACH ROW
    WHEN (NEW.direction = 'outbound')
    EXECUTE FUNCTION check_opt_out();

-- Auto-add to opt_outs when lead status is do_not_call
CREATE OR REPLACE FUNCTION sync_dnc_to_optouts()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.do_not_call = true AND NEW.phone IS NOT NULL THEN
        INSERT INTO opt_outs (phone, source)
        VALUES (NEW.phone, 'manual')
        ON CONFLICT (phone) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_dnc_trigger
    AFTER UPDATE OF do_not_call ON leads
    FOR EACH ROW
    WHEN (NEW.do_not_call = true)
    EXECUTE FUNCTION sync_dnc_to_optouts();

-- Count daily contact attempts (FTSA compliance: max 3 per 24h)
CREATE OR REPLACE FUNCTION count_daily_contacts(p_lead_id INTEGER)
RETURNS INTEGER AS $$
    SELECT COUNT(*)::INTEGER
    FROM interactions
    WHERE lead_id = p_lead_id
      AND direction = 'outbound'
      AND created_at > NOW() - INTERVAL '24 hours';
$$ LANGUAGE sql STABLE;

-- View: leads ready to contact
CREATE OR REPLACE VIEW contactable_leads AS
SELECT l.*
FROM leads l
WHERE l.status NOT IN ('do_not_call', 'closed_won', 'closed_lost')
  AND l.do_not_call = false
  AND l.phone IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM opt_outs o WHERE o.phone = l.phone)
  AND count_daily_contacts(l.id) < 3
ORDER BY l.renovation_score DESC, l.created_at ASC;
