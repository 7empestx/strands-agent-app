import { useNavigate } from 'react-router';
import styled from 'styled-components';

const SidebarContainer = styled.nav`
  width: 60px;
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
`;

const Logo = styled.div`
  width: 40px;
  height: 40px;
  background: #e94560;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  cursor: pointer;
  transition: transform 0.2s ease;

  &:hover {
    transform: scale(1.05);
  }
`;

function Sidebar() {
  const navigate = useNavigate();

  return (
    <SidebarContainer>
      <Logo onClick={() => navigate('/alerts')} title="Clippy Alerts">
        📎
      </Logo>
    </SidebarContainer>
  );
}

export default Sidebar;
