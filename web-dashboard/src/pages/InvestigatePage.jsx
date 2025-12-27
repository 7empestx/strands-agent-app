import { useState, useEffect } from 'react';
import { useParams } from 'react-router';
import styled from 'styled-components';
import {
  Button,
  Chip,
  BouncingDotsIcon,
} from '@mrrobot/cast-component-library';
import { getIncidentDetails, analyzeIncident } from '../api/clippy';

const PageContainer = styled.div`
  max-width: 1200px;
`;

const Header = styled.div`
  margin-bottom: 24px;
`;

const Breadcrumb = styled.div`
  font-size: 13px;
  color: #6b6b80;
  margin-bottom: 8px;

  a {
    color: #6b6b80;
    text-decoration: none;
    &:hover {
      color: #1a1a2e;
    }
  }
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 12px 0;
`;

const MetaRow = styled.div`
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
`;

const TwoColumn = styled.div`
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 24px;

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
`;

const MainPanel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const SidePanel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const Card = styled.div`
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
`;

const CardTitle = styled.h3`
  font-size: 14px;
  font-weight: 600;
  color: #6b6b80;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 16px 0;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const AIAnalysisCard = styled(Card)`
  border: 2px solid #e94560;
  background: linear-gradient(135deg, #fff 0%, #fef5f7 100%);
`;

const AnalysisSection = styled.div`
  margin-bottom: 16px;

  &:last-child {
    margin-bottom: 0;
  }
`;

const SectionTitle = styled.h4`
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 8px 0;
`;

const SectionContent = styled.p`
  font-size: 14px;
  color: #1a1a2e;
  margin: 0;
  line-height: 1.6;
`;

const CodeBlock = styled.pre`
  background: #1a1a2e;
  color: #f8f8f2;
  padding: 16px;
  border-radius: 8px;
  font-size: 13px;
  overflow-x: auto;
  margin: 8px 0 0 0;
`;

const LogEntry = styled.div`
  padding: 12px;
  border-bottom: 1px solid #f0f0f5;
  font-family: monospace;
  font-size: 12px;

  &:last-child {
    border-bottom: none;
  }
`;

const LogTimestamp = styled.span`
  color: #6b6b80;
  margin-right: 12px;
`;

const LogLevel = styled.span`
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  margin-right: 8px;
  background: ${props => {
    switch (props.$level) {
      case 'error': return '#fee2e2';
      case 'warn': return '#fef3c7';
      case 'info': return '#dbeafe';
      default: return '#f3f4f6';
    }
  }};
  color: ${props => {
    switch (props.$level) {
      case 'error': return '#dc2626';
      case 'warn': return '#d97706';
      case 'info': return '#2563eb';
      default: return '#6b7280';
    }
  }};
`;

const ActionList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const ActionItem = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #f8f9fc;
  border-radius: 8px;
  font-size: 14px;

  svg {
    width: 18px;
    height: 18px;
    color: #27ae60;
  }
`;

const LoadingState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: #6b6b80;
`;

// Mock data
const MOCK_INCIDENT = {
  id: 'P2345678',
  title: 'Critical Alert: BROKER TABLES [PROD] - Sustained High Latency',
  status: 'triggered',
  urgency: 'high',
  service: 'cast-core-service',
  created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
  description: 'Database queries on broker_transactions table exceeding 5s response time. Affecting syncAll endpoint.',
};

const MOCK_ANALYSIS = {
  summary: 'The syncAll endpoint is experiencing sustained high latency (5-15s response times) due to full table scans on broker_transactions. The table has grown to 2.3M rows without appropriate indexing on the created_at column used in the WHERE clause.',
  root_cause: 'Missing index on broker_transactions.created_at combined with inefficient query pattern that fetches all columns.',
  affected_code: {
    file: 'src/services/brokerService.js',
    line: 145,
    snippet: `async function syncAll(merchantId, fromDate) {
  // Problem: Full table scan without index
  const transactions = await db.query(
    'SELECT * FROM broker_transactions WHERE merchant_id = ? AND created_at > ?',
    [merchantId, fromDate]
  );
  return transactions;
}`,
  },
  suggested_fixes: [
    'Add composite index: CREATE INDEX idx_broker_merchant_date ON broker_transactions(merchant_id, created_at)',
    'Implement pagination: Add LIMIT/OFFSET or cursor-based pagination',
    'Select specific columns instead of SELECT *',
    'Consider adding read replica for heavy queries',
  ],
  similar_issues: [
    { date: '2024-10-07', resolution: 'Increased Lambda timeout to 60s as temporary fix' },
    { date: '2024-09-15', resolution: 'Added index on similar table, reduced query time by 80%' },
  ],
};

const MOCK_LOGS = [
  { timestamp: '2024-12-25T05:45:23Z', level: 'error', message: 'Query timeout after 30000ms: SELECT * FROM broker_transactions WHERE merchant_id = ?' },
  { timestamp: '2024-12-25T05:44:18Z', level: 'warn', message: 'Slow query detected: 8543ms for syncAll(merchant_id=abc123)' },
  { timestamp: '2024-12-25T05:43:55Z', level: 'error', message: '504 Gateway Timeout on POST /api/v1/sync/all' },
  { timestamp: '2024-12-25T05:42:30Z', level: 'info', message: 'syncAll started for merchant abc123, date range: 30 days' },
  { timestamp: '2024-12-25T05:41:12Z', level: 'warn', message: 'Memory usage at 78% for Lambda function cast-core-syncAll' },
];

function InvestigatePage() {
  const { incidentId } = useParams();
  const [incident, setIncident] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    loadIncidentData();
  }, [incidentId]);

  const loadIncidentData = async () => {
    setLoading(true);
    try {
      // Try real API first, fall back to mock data
      try {
        const data = await getIncidentDetails(incidentId);
        setIncident(data.incident);
        setLogs(data.recent_logs || []);

        // Get AI analysis
        setAnalyzing(true);
        const analysisData = await analyzeIncident(incidentId);
        setAnalysis(analysisData.analysis);
        setAnalyzing(false);
      } catch (apiError) {
        console.warn('API not available, using mock data:', apiError.message);
        // Fallback to mock data for development
        await new Promise(resolve => setTimeout(resolve, 600));
        setIncident(MOCK_INCIDENT);
        setLogs(MOCK_LOGS);

        setAnalyzing(true);
        await new Promise(resolve => setTimeout(resolve, 1200));
        setAnalysis(MOCK_ANALYSIS);
        setAnalyzing(false);
      }
    } catch (error) {
      console.error('Failed to load incident:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <LoadingState>
        <BouncingDotsIcon />
        <p>Loading incident details...</p>
      </LoadingState>
    );
  }

  return (
    <PageContainer>
      <Header>
        <Breadcrumb>
          <a href="/alerts">Alerts</a> / {incidentId}
        </Breadcrumb>
        <Title>{incident?.title}</Title>
        <MetaRow>
          <Chip color="red">{incident?.status}</Chip>
          <Chip color="blue">{incident?.service}</Chip>
          <Chip color="orange">Urgency: {incident?.urgency}</Chip>
        </MetaRow>
      </Header>

      <TwoColumn>
        <MainPanel>
          {/* AI Analysis */}
          <AIAnalysisCard>
            <CardTitle>
              <span>🤖</span> AI Analysis
              {analyzing && <BouncingDotsIcon />}
            </CardTitle>

            {analysis ? (
              <>
                <AnalysisSection>
                  <SectionTitle>Summary</SectionTitle>
                  <SectionContent>{analysis.summary}</SectionContent>
                </AnalysisSection>

                <AnalysisSection>
                  <SectionTitle>Root Cause</SectionTitle>
                  <SectionContent>{analysis.root_cause}</SectionContent>
                </AnalysisSection>

                <AnalysisSection>
                  <SectionTitle>Affected Code</SectionTitle>
                  <SectionContent>
                    <strong>{analysis.affected_code.file}</strong> (line {analysis.affected_code.line})
                  </SectionContent>
                  <CodeBlock>{analysis.affected_code.snippet}</CodeBlock>
                </AnalysisSection>
              </>
            ) : (
              <SectionContent>Analyzing incident...</SectionContent>
            )}
          </AIAnalysisCard>

          {/* Suggested Fixes */}
          {analysis?.suggested_fixes && (
            <Card>
              <CardTitle>
                <span>✅</span> Suggested Fixes
              </CardTitle>
              <ActionList>
                {analysis.suggested_fixes.map((fix, idx) => (
                  <ActionItem key={idx}>
                    <span>✓</span>
                    {fix}
                  </ActionItem>
                ))}
              </ActionList>
            </Card>
          )}

          {/* Related Logs */}
          <Card>
            <CardTitle>
              <span>📋</span> Related Logs
            </CardTitle>
            {logs.map((log, idx) => (
              <LogEntry key={idx}>
                <LogTimestamp>
                  {new Date(log.timestamp).toLocaleTimeString()}
                </LogTimestamp>
                <LogLevel $level={log.level}>{log.level.toUpperCase()}</LogLevel>
                {log.message}
              </LogEntry>
            ))}
          </Card>
        </MainPanel>

        <SidePanel>
          {/* Quick Actions */}
          <Card>
            <CardTitle>Quick Actions</CardTitle>
            <ActionList>
              <Button variant="primary" fullWidth>
                Create Jira Ticket
              </Button>
              <Button variant="secondary" fullWidth>
                Acknowledge Incident
              </Button>
              <Button variant="secondary" fullWidth>
                View in PagerDuty
              </Button>
              <Button variant="secondary" fullWidth>
                View Full Logs
              </Button>
            </ActionList>
          </Card>

          {/* Similar Past Issues */}
          {analysis?.similar_issues && (
            <Card>
              <CardTitle>
                <span>⚠️</span> Similar Past Issues
              </CardTitle>
              {analysis.similar_issues.map((issue, idx) => (
                <AnalysisSection key={idx}>
                  <SectionTitle>{issue.date}</SectionTitle>
                  <SectionContent>{issue.resolution}</SectionContent>
                </AnalysisSection>
              ))}
            </Card>
          )}

          {/* Incident Details */}
          <Card>
            <CardTitle>Incident Details</CardTitle>
            <AnalysisSection>
              <SectionTitle>ID</SectionTitle>
              <SectionContent>{incident?.id}</SectionContent>
            </AnalysisSection>
            <AnalysisSection>
              <SectionTitle>Created</SectionTitle>
              <SectionContent>
                {new Date(incident?.created_at).toLocaleString()}
              </SectionContent>
            </AnalysisSection>
            <AnalysisSection>
              <SectionTitle>Service</SectionTitle>
              <SectionContent>{incident?.service}</SectionContent>
            </AnalysisSection>
          </Card>
        </SidePanel>
      </TwoColumn>
    </PageContainer>
  );
}

export default InvestigatePage;
