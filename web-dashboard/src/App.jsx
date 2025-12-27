import { useState, useEffect } from 'react';
import { Outlet } from 'react-router';
import styled from 'styled-components';
import Sidebar from './components/Sidebar';
import ChatBot from './components/ChatBot';

const AppContainer = styled.div`
  display: flex;
  min-height: 100vh;
`;

const MainContent = styled.main`
  flex: 1;
  display: flex;
  flex-direction: column;
`;

const Header = styled.header`
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
`;

const HeaderTitle = styled.h1`
  color: white;
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  flex: 1;
`;

const UserSection = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const UserInfo = styled.span`
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
`;

const LogoutButton = styled.button`
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.2);
  }
`;

const ContentArea = styled.div`
  flex: 1;
  padding: 24px;
  background-color: #f5f7fa;
  overflow-y: auto;
`;

function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // Fetch current user info
    fetch('/api/user')
      .then(res => {
        if (res.ok) return res.json();
        if (res.status === 401) {
          // Not logged in - redirect to login
          window.location.href = '/auth/login';
          return null;
        }
        return null;
      })
      .then(data => {
        if (data) setUser(data);
        setAuthChecked(true);
      })
      .catch(() => {
        // Auth not configured - allow access without login
        setAuthChecked(true);
      });
  }, []);

  // Show loading while checking auth
  if (!authChecked) {
    return (
      <AppContainer>
        <MainContent style={{ justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ color: '#666' }}>Loading...</div>
        </MainContent>
      </AppContainer>
    );
  }

  const handleLogout = () => {
    window.location.href = '/auth/logout';
  };

  return (
    <AppContainer>
      <Sidebar />
      <MainContent>
        <Header>
          <HeaderTitle>Clippy Alerts Dashboard</HeaderTitle>
          {user && (
            <UserSection>
              <UserInfo>{user.name || user.email}</UserInfo>
              <LogoutButton onClick={handleLogout}>Logout</LogoutButton>
            </UserSection>
          )}
        </Header>
        <ContentArea>
          <Outlet />
        </ContentArea>
      </MainContent>
      <ChatBot />
    </AppContainer>
  );
}

export default App;
