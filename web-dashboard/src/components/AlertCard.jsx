import { useNavigate } from 'react-router';
import styled from 'styled-components';
import {
  Button,
  Chip,
} from '@mrrobot/cast-component-library';

const Card = styled.div`
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border-left: 4px solid ${props => {
    switch (props.$status) {
      case 'triggered': return '#e94560';
      case 'acknowledged': return '#f5a623';
      case 'resolved': return '#27ae60';
      default: return '#8b8b9e';
    }
  }};
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  }
`;

const Header = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
`;

const StatusBadge = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  background: ${props => {
    switch (props.$status) {
      case 'triggered': return 'rgba(233, 69, 96, 0.1)';
      case 'acknowledged': return 'rgba(245, 166, 35, 0.1)';
      case 'resolved': return 'rgba(39, 174, 96, 0.1)';
      default: return 'rgba(139, 139, 158, 0.1)';
    }
  }};
  color: ${props => {
    switch (props.$status) {
      case 'triggered': return '#e94560';
      case 'acknowledged': return '#f5a623';
      case 'resolved': return '#27ae60';
      default: return '#8b8b9e';
    }
  }};

  svg {
    width: 14px;
    height: 14px;
  }
`;

const Title = styled.h3`
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 8px 0;
  line-height: 1.4;
`;

const Meta = styled.div`
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
`;

const MetaItem = styled.span`
  font-size: 13px;
  color: #6b6b80;
`;

const AIAnalysis = styled.div`
  background: #f8f9fc;
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 16px;
`;

const AIHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #6b6b80;
  text-transform: uppercase;
`;

const AIContent = styled.p`
  font-size: 14px;
  color: #1a1a2e;
  margin: 0;
  line-height: 1.5;
`;

const SuggestedFix = styled.div`
  background: rgba(39, 174, 96, 0.08);
  border: 1px solid rgba(39, 174, 96, 0.2);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
`;

const FixHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #27ae60;
  margin-bottom: 6px;

  svg {
    width: 14px;
    height: 14px;
  }
`;

const FixContent = styled.p`
  font-size: 13px;
  color: #1a1a2e;
  margin: 0;
`;

const Actions = styled.div`
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
`;

const StatusIcon = ({ status }) => {
  switch (status) {
    case 'triggered':
      return <span>🔴</span>;
    case 'acknowledged':
      return <span>🟡</span>;
    case 'resolved':
      return <span>🟢</span>;
    default:
      return <span>⚪</span>;
  }
};

function AlertCard({ incident, analysis }) {
  const navigate = useNavigate();

  const formatTime = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <Card $status={incident.status}>
      <Header>
        <div>
          <StatusBadge $status={incident.status}>
            <StatusIcon status={incident.status} />
            {incident.status}
          </StatusBadge>
        </div>
        <MetaItem>{formatTime(incident.created_at)}</MetaItem>
      </Header>

      <Title>{incident.title}</Title>

      <Meta>
        {incident.service && (
          <Chip color="blue" size="small">{incident.service}</Chip>
        )}
        {incident.urgency && (
          <Chip
            color={incident.urgency === 'high' ? 'red' : 'gray'}
            size="small"
          >
            {incident.urgency}
          </Chip>
        )}
      </Meta>

      {analysis && (
        <>
          <AIAnalysis>
            <AIHeader>
              <span>🤖</span> AI Analysis
            </AIHeader>
            <AIContent>{analysis.summary}</AIContent>
          </AIAnalysis>

          {analysis.suggested_fix && (
            <SuggestedFix>
              <FixHeader>
                <span>✅</span>
                Suggested Fix
              </FixHeader>
              <FixContent>{analysis.suggested_fix}</FixContent>
            </SuggestedFix>
          )}
        </>
      )}

      <Actions>
        <Button
          variant="primary"
          size="small"
          onClick={() => navigate(`/investigate/${incident.id}`)}
        >
          Investigate
        </Button>
        <Button
          variant="secondary"
          size="small"
          onClick={() => window.open(incident.html_url, '_blank')}
        >
          View in PagerDuty
        </Button>
        {analysis?.code_location && (
          <Button
            variant="secondary"
            size="small"
            onClick={() => window.open(analysis.code_location, '_blank')}
          >
            View Code
          </Button>
        )}
      </Actions>
    </Card>
  );
}

export default AlertCard;
