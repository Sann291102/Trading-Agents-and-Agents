/** Mirrors aio.models.product -- the Product Manager's typed output. */

export interface UserStory {
  as_a: string;
  i_want: string;
  so_that: string;
  acceptance_criteria: string[];
}

export interface Epic {
  title: string;
  description: string;
  user_stories: UserStory[];
}

export interface ProductVision {
  statement: string;
  target_users: string[];
  value_proposition: string;
}

export interface Risk {
  description: string;
  likelihood: string;
  impact: string;
  mitigation: string;
}

export interface SuccessMetric {
  name: string;
  target: string;
  rationale: string;
}

export interface ReleasePhase {
  name: string;
  scope: string;
  epics: string[];
}

export interface BusinessRequirementsDocument {
  vision: ProductVision;
  epics: Epic[];
  release_roadmap: ReleasePhase[];
  sprint_suggestions: string[];
  risk_register: Risk[];
  success_metrics: SuccessMetric[];
  confidence: number;
  reasoning_summary: string;
}
