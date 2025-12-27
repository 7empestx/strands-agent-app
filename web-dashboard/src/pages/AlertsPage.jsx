import { useState, useEffect } from 'react';
import styled from 'styled-components';
import {
  Button,
  SegmentedControl,
  Input,
  BouncingDotsIcon,
} from '@mrrobot/cast-component-library';
import AlertCard from '../components/AlertCard';
import { getActiveIncidents } from '../api/clippy';

const PageHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
`;

const Title = styled.h1`
  font-size: 20px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const AlertCount = styled.span`
  background: #e94560;
  color: white;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
`;

const StatsBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
  padding: 14px 20px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
`;

const StatsLeft = styled.div`
  display: flex;
  gap: 24px;
`;

const StatsCenter = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  justify-content: center;
  max-width: 500px;
`;

const StatsRight = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const Stat = styled.div`
  display: flex;
  flex-direction: column;
`;

const StatValue = styled.span`
  font-size: 24px;
  font-weight: 700;
  color: ${props => props.$color || '#1a1a2e'};
`;

const StatLabel = styled.span`
  font-size: 12px;
  color: #6b6b80;
`;

const AlertsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
`;

const LoadingState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: #6b6b80;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 60px;
  color: #6b6b80;

  h3 {
    font-size: 18px;
    margin-bottom: 8px;
    color: #1a1a2e;
  }
`;

// Mock data for demo - will be replaced with real API calls
const MOCK_INCIDENTS = [
  {
    id: 'P1234567',
    title: 'CSP Violation - Warning - emvio-dashboard-app',
    status: 'triggered',
    urgency: 'high',
    service: 'emvio-dashboard-app',
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    html_url: 'https://mrrobot.pagerduty.com/incidents/P1234567',
  },
  {
    id: 'P2345678',
    title: 'Critical Alert: BROKER TABLES [PROD] - Sustained High Latency',
    status: 'triggered',
    urgency: 'high',
    service: 'cast-core-service',
    created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    html_url: 'https://mrrobot.pagerduty.com/incidents/P2345678',
  },
  {
    id: 'P3456789',
    title: '504 Gateway Timeout on syncAll endpoint',
    status: 'acknowledged',
    urgency: 'high',
    service: 'cast-core-service',
    created_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    html_url: 'https://mrrobot.pagerduty.com/incidents/P3456789',
  },
  {
    id: 'P4567890',
    title: 'ECS Memory Utilization > 85%',
    status: 'triggered',
    urgency: 'low',
    service: 'mrrobot-mcp-server',
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    html_url: 'https://mrrobot.pagerduty.com/incidents/P4567890',
  },
];

const MOCK_ANALYSES = {
  'P1234567': {
    summary: 'CORS headers missing on /api/v2/upload endpoint. Browser blocking cross-origin requests from dashboard.mrrobotpaydev.com.',
    suggested_fix: 'Add AllowedOrigins configuration to the S3 bucket CORS policy for the dev environment.',
    code_location: 'https://bitbucket.org/mrrobot-labs/emvio-dashboard-app/src/main/src/api/upload.js',
  },
  'P2345678': {
    summary: 'Database queries taking >5s on broker tables. High lock contention detected during peak hours.',
    suggested_fix: 'Consider adding index on broker_transactions.created_at column and optimizing the syncAll query.',
    code_location: 'https://bitbucket.org/mrrobot-labs/cast-core-service/src/main/src/services/brokerService.js',
  },
  'P3456789': {
    summary: 'Lambda timeout (30s) exceeded. syncAll processing large dataset (50k+ records).',
    suggested_fix: 'Increase Lambda timeout to 60s or implement pagination for large syncs.',
    code_location: 'https://bitbucket.org/mrrobot-labs/cast-core-service/src/main/src/handlers/syncAll.js',
  },
  'P4567890': {
    summary: 'Memory creeping up over time. Possible memory leak in bedrock client connection pooling.',
    suggested_fix: 'Review bedrock_client.py for connection cleanup. Consider adding explicit close() calls.',
    code_location: 'https://bitbucket.org/mrrobot-labs/strands-agent-app/src/main/src/mcp_server/slack_bot/bedrock_client.py',
  },
};

function AlertsPage() {
  const [incidents, setIncidents] = useState([]);
  const [analyses, setAnalyses] = useState({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadIncidents();
  }, []);

  const loadIncidents = async () => {
    setLoading(true);
    try {
      // Try real API first, fall back to mock data
      try {
        const data = await getActiveIncidents();
        // Transform API response to component format
        const incidentsList = data.incidents.map(item => item.incident);
        const analysesMap = {};
        data.incidents.forEach(item => {
          analysesMap[item.incident.id] = item.analysis;
        });
        setIncidents(incidentsList);
        setAnalyses(analysesMap);
      } catch (apiError) {
        console.warn('API not available, using mock data:', apiError.message);
        // Fallback to mock data for development
        await new Promise(resolve => setTimeout(resolve, 800));
        setIncidents(MOCK_INCIDENTS);
        setAnalyses(MOCK_ANALYSES);
      }
    } catch (error) {
      console.error('Failed to load incidents:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredIncidents = incidents.filter(incident => {
    if (filter !== 'all' && incident.status !== filter) return false;
    if (searchQuery && !incident.title.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  const stats = {
    triggered: incidents.filter(i => i.status === 'triggered').length,
    acknowledged: incidents.filter(i => i.status === 'acknowledged').length,
    total: incidents.length,
  };

  if (loading) {
    return (
      <LoadingState>
        <BouncingDotsIcon />
        <p>Loading alerts...</p>
      </LoadingState>
    );
  }

  return (
    <>
      <PageHeader>
        <Title>
          Active Alerts
          {stats.triggered > 0 && (
            <AlertCount>{stats.triggered} triggered</AlertCount>
          )}
        </Title>
      </PageHeader>

      <StatsBar>
        <StatsLeft>
          <Stat>
            <StatValue $color="#e94560">{stats.triggered}</StatValue>
            <StatLabel>Triggered</StatLabel>
          </Stat>
          <Stat>
            <StatValue $color="#f5a623">{stats.acknowledged}</StatValue>
            <StatLabel>Acknowledged</StatLabel>
          </Stat>
          <Stat>
            <StatValue>{stats.total}</StatValue>
            <StatLabel>Total</StatLabel>
          </Stat>
        </StatsLeft>

        <StatsCenter>
          <Input
            placeholder="Search alerts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: '100%', minWidth: 180 }}
          />
          <SegmentedControl
            options={[
              { value: 'all', label: 'All' },
              { value: 'triggered', label: 'Triggered' },
              { value: 'acknowledged', label: 'Acked' },
            ]}
            value={filter}
            onChange={setFilter}
          />
        </StatsCenter>

        <StatsRight>
          <Button
            variant="secondary"
            onClick={loadIncidents}
          >
            Refresh
          </Button>
        </StatsRight>
      </StatsBar>

      {filteredIncidents.length === 0 ? (
        <EmptyState>
          <h3>No alerts found</h3>
          <p>
            {filter === 'all'
              ? 'All clear! No active incidents.'
              : `No ${filter} incidents at the moment.`}
          </p>
        </EmptyState>
      ) : (
        <AlertsGrid>
          {filteredIncidents.map(incident => (
            <AlertCard
              key={incident.id}
              incident={incident}
              analysis={analyses[incident.id]}
            />
          ))}
        </AlertsGrid>
      )}
    </>
  );
}

export default AlertsPage;
