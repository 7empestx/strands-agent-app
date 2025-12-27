import { useState, useEffect, useRef } from 'react';
import styled from 'styled-components';
import ReactMarkdown from 'react-markdown';
import { Button, BouncingDotsIcon } from '@mrrobot/cast-component-library';

const ChatContainer = styled.div`
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
`;

const ChatButton = styled.button`
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e94560 0%, #d63c55 100%);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  box-shadow: 0 4px 16px rgba(233, 69, 96, 0.4);
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 20px rgba(233, 69, 96, 0.5);
  }
`;

const ChatPanel = styled.div`
  position: absolute;
  bottom: 70px;
  right: 0;
  width: 400px;
  height: 500px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;

  @media (max-width: 500px) {
    width: calc(100vw - 48px);
    height: 60vh;
  }
`;

const ChatHeader = styled.div`
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
`;

const ChatTitle = styled.h3`
  color: white;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  flex: 1;
`;

const CloseButton = styled.button`
  background: transparent;
  border: none;
  color: white;
  cursor: pointer;
  font-size: 20px;
  opacity: 0.8;
  &:hover {
    opacity: 1;
  }
`;

const MessagesContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
`;

const Message = styled.div`
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;

  ${props => props.$role === 'user' ? `
    align-self: flex-end;
    background: #e94560;
    color: white;
    border-bottom-right-radius: 4px;
  ` : `
    align-self: flex-start;
    background: #f5f7fa;
    color: #1a1a2e;
    border-bottom-left-radius: 4px;
  `}

  pre {
    background: #1a1a2e;
    color: #f8f8f2;
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 12px;
    margin: 8px 0;
  }

  code {
    background: rgba(0, 0, 0, 0.1);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
  }
`;

const ToolIndicator = styled.div`
  align-self: flex-start;
  padding: 8px 12px;
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 8px;
  font-size: 12px;
  color: #856404;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const InputContainer = styled.div`
  padding: 12px 16px;
  border-top: 1px solid #e0e0e0;
  display: flex;
  gap: 8px;
`;

const Input = styled.input`
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
  outline: none;

  &:focus {
    border-color: #e94560;
  }

  &:disabled {
    background: #f5f5f5;
  }
`;

const WelcomeMessage = styled.div`
  text-align: center;
  padding: 24px;
  color: #6b6b80;

  h4 {
    margin: 0 0 8px 0;
    color: #1a1a2e;
  }

  p {
    margin: 0;
    font-size: 13px;
  }
`;

function ChatBot() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentTool, setCurrentTool] = useState(null);
  const [streamingContent, setStreamingContent] = useState('');

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Connect to WebSocket when chat opens
  useEffect(() => {
    if (isOpen && !wsRef.current) {
      connectWebSocket();
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isOpen]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/chat`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('[Chat] WebSocket connected');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      };

      ws.onclose = () => {
        console.log('[Chat] WebSocket disconnected');
        setIsConnected(false);
        wsRef.current = null;
      };

      ws.onerror = (error) => {
        console.error('[Chat] WebSocket error:', error);
        setIsConnected(false);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('[Chat] Failed to connect:', error);
    }
  };

  const handleWebSocketMessage = (data) => {
    switch (data.type) {
      case 'status':
        setIsLoading(data.status === 'thinking');
        break;

      case 'token':
        setStreamingContent(prev => prev + data.content);
        break;

      case 'tool_start':
        setCurrentTool(data.name);
        break;

      case 'tool_executing':
        setCurrentTool(`Running ${data.name}...`);
        break;

      case 'tool_end':
        setCurrentTool(null);
        break;

      case 'done':
        // Finalize the assistant message
        if (streamingContent) {
          setMessages(prev => [...prev, { role: 'assistant', content: streamingContent }]);
          setStreamingContent('');
        }
        setIsLoading(false);
        setCurrentTool(null);
        break;

      case 'error':
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.message}` }]);
        setIsLoading(false);
        setCurrentTool(null);
        setStreamingContent('');
        break;

      case 'pong':
        // Heartbeat response, ignore
        break;

      default:
        console.log('[Chat] Unknown message type:', data.type);
    }
  };

  const sendMessage = () => {
    if (!input.trim() || !wsRef.current || isLoading) return;

    const userMessage = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setInput('');
    setIsLoading(true);
    setStreamingContent('');

    wsRef.current.send(JSON.stringify({
      type: 'message',
      content: userMessage,
    }));
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <ChatContainer>
      {isOpen && (
        <ChatPanel>
          <ChatHeader>
            <span style={{ fontSize: '24px' }}>&#128206;</span>
            <ChatTitle>Clippy Assistant</ChatTitle>
            <CloseButton onClick={() => setIsOpen(false)}>x</CloseButton>
          </ChatHeader>

          <MessagesContainer>
            {messages.length === 0 && !streamingContent && (
              <WelcomeMessage>
                <h4>Hi! I'm Clippy</h4>
                <p>Ask me about logs, alerts, deployments, code, or anything DevOps-related.</p>
              </WelcomeMessage>
            )}

            {messages.map((msg, idx) => (
              <Message key={idx} $role={msg.role}>
                {msg.role === 'assistant' ? (
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                ) : (
                  msg.content
                )}
              </Message>
            ))}

            {streamingContent && (
              <Message $role="assistant">
                <ReactMarkdown>{streamingContent}</ReactMarkdown>
              </Message>
            )}

            {currentTool && (
              <ToolIndicator>
                <BouncingDotsIcon />
                {currentTool}
              </ToolIndicator>
            )}

            {isLoading && !streamingContent && !currentTool && (
              <ToolIndicator>
                <BouncingDotsIcon />
                Thinking...
              </ToolIndicator>
            )}

            <div ref={messagesEndRef} />
          </MessagesContainer>

          <InputContainer>
            <Input
              type="text"
              placeholder={isConnected ? "Ask Clippy..." : "Connecting..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={!isConnected || isLoading}
            />
            <Button
              variant="primary"
              onClick={sendMessage}
              disabled={!isConnected || isLoading || !input.trim()}
            >
              Send
            </Button>
          </InputContainer>
        </ChatPanel>
      )}

      <ChatButton onClick={() => setIsOpen(!isOpen)} title="Chat with Clippy">
        {isOpen ? 'x' : '📎'}
      </ChatButton>
    </ChatContainer>
  );
}

export default ChatBot;
