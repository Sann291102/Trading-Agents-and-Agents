/** Mirrors aio.models.research -- the Research & Planning department's
 * typed output contracts. */

export interface DomainKnowledgeReport {
  industry: string;
  terminology: string[];
  business_workflows: string[];
  compliance_concerns: string[];
  industry_standards: string[];
  user_personas: string[];
  business_constraints: string[];
  kpis: string[];
  pain_points: string[];
  domain_risks: string[];
  confidence: number;
  reasoning_summary: string;
}

export interface MarketResearchReport {
  target_users: string[];
  existing_products: string[];
  market_size_estimate: string;
  pricing_landscape: string;
  customer_expectations: string[];
  emerging_trends: string[];
  technology_adoption: string[];
  confidence: number;
  reasoning_summary: string;
}

export interface CompetitorProfile {
  name: string;
  features: string[];
  pricing: string;
  architecture: string;
  technology: string;
  strengths: string[];
  weaknesses: string[];
  differentiators: string[];
}

export interface FeatureGap {
  feature: string;
  our_status: string;
  competitor_status: string;
  notes: string;
}

export interface SWOTAnalysis {
  strengths: string[];
  weaknesses: string[];
  opportunities: string[];
  threats: string[];
}

export interface CompetitorMatrix {
  competitors: CompetitorProfile[];
  swot: SWOTAnalysis;
  feature_gaps: FeatureGap[];
  confidence: number;
  reasoning_summary: string;
}

export interface TechnicalResearchReport {
  frameworks: string[];
  cloud_services: string[];
  architecture_patterns: string[];
  existing_apis: string[];
  sdks: string[];
  integration_possibilities: string[];
  licensing_notes: string[];
  performance_benchmarks: string[];
  confidence: number;
  reasoning_summary: string;
}

export interface ResearchReport {
  executive_summary: string;
  opportunities: string[];
  risks: string[];
  assumptions: string[];
  recommended_direction: string;
  supporting_evidence: string[];
  confidence: number;
  reasoning_summary: string;
  domain: DomainKnowledgeReport;
  market: MarketResearchReport;
  competitor: CompetitorMatrix;
  technical: TechnicalResearchReport;
}
