ALTER TABLE proposals ADD COLUMN report_id uuid, ADD COLUMN report_proposal_key text;
CREATE UNIQUE INDEX proposal_report_source ON proposals(report_id, report_proposal_key)
  WHERE report_id IS NOT NULL;
