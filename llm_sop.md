# Standard Operating Procedure for using LLMs for Coding

1. Share `player.py` with Claude and iteratively generate a 12-part development plan
2. Give Gemini Pro the context for upgrading the codebase and ask it to develop an implementation plan for Phase 1
3. Share this implementation plan with Gemini Flash and ask it to make improvements
4. Share this revised implementation plan and original upgradation context with Gemini Flash and ask it to implement it. It does the job.
5. Ask Gemini Flash to break `player.py` down into smaller scripts and add a meaningful description for each. It does the job.
6. Repeat Steps 2-4 for each subsequent phase of development.

### Step 2 Prompt

```
  I want to add Multi-Client Independent HLS Streaming with Server-Side Playback Control to this server.

  Here's my larger plan –

  '''
  ## Implementation Priority Order

  1. **Basic HLS Infrastructure** (Single-client HLS streaming, FFmpeg integration, HTTP serving)
  2. **Client Architecture Foundation** (ID management, registration, basic client types)
  3. **WebSocket Protocol Enhancement** (HLS-specific commands, basic client routing)
  4. **Early Testing Framework** (Single-client HLS validation, basic stream control)
  5. **Multi-Process HLS Architecture** (Per-client FFmpeg processes, resource management)
  6. **Independent Queue Management** (Per-client queues, queue operations)
  7. **Server-Side Playback Control** (Authority management, takeover protocol)
  8. **Enhanced Client Management** (Advanced client status monitoring, capabilities)
  9. **Resource Management & Optimization** (Process limiting, cleanup, monitoring)
  10. **Synchronization Features** (Optional coordination between clients)
  11. **Error Handling and Recovery** (Failure scenarios, cleanup)
  12. **Advanced Testing and Optimization** (Performance tuning, validation)
  '''

  I have already implemented Phase 1-X. 

  I have developed a plan for implementing Phase X based on this guidance –

  '''
  <THE PHASE X PLAN FROM upgrade_plan.md>
  '''

  Write the implementation plan with specifics.
```

### Step 3 Prompt

```
  I want to add Multi-Client Independent HLS Streaming with Server-Side Playback Control to this server.

  Here's my larger plan –

  '''
  ## Implementation Priority Order

  1. **Basic HLS Infrastructure** (Single-client HLS streaming, FFmpeg integration, HTTP serving)
  2. **Client Architecture Foundation** (ID management, registration, basic client types)
  3. **WebSocket Protocol Enhancement** (HLS-specific commands, basic client routing)
  4. **Early Testing Framework** (Single-client HLS validation, basic stream control)
  5. **Multi-Process HLS Architecture** (Per-client FFmpeg processes, resource management)
  6. **Independent Queue Management** (Per-client queues, queue operations)
  7. **Server-Side Playback Control** (Authority management, takeover protocol)
  8. **Enhanced Client Management** (Advanced client status monitoring, capabilities)
  9. **Resource Management & Optimization** (Process limiting, cleanup, monitoring)
  10. **Synchronization Features** (Optional coordination between clients)
  11. **Error Handling and Recovery** (Failure scenarios, cleanup)
  12. **Advanced Testing and Optimization** (Performance tuning, validation)
  '''

  I have already implemented Phase 1-X. 

  I have developed a plan for implementing Phase X based on this guidance –

  '''
  <THE PHASE X PLAN FROM upgrade_plan.md>
  '''

  Here's a development plan for Phase X, detailing the specific changes needed in the existing files -

  '''
  <THE IMPLEMENTATION PLAN FROM STEP 2>
  '''

  Is this a good implementation plan? Update it if there are any items that need improvement.
```

### Step 4 Prompt

```
  I want to add Multi-Client Independent HLS Streaming with Server-Side Playback Control to this server.

  Here's my larger plan –

  '''
  ## Implementation Priority Order

  1. **Basic HLS Infrastructure** (Single-client HLS streaming, FFmpeg integration, HTTP serving)
  2. **Client Architecture Foundation** (ID management, registration, basic client types)
  3. **WebSocket Protocol Enhancement** (HLS-specific commands, basic client routing)
  4. **Early Testing Framework** (Single-client HLS validation, basic stream control)
  5. **Multi-Process HLS Architecture** (Per-client FFmpeg processes, resource management)
  6. **Independent Queue Management** (Per-client queues, queue operations)
  7. **Server-Side Playback Control** (Authority management, takeover protocol)
  8. **Enhanced Client Management** (Advanced client status monitoring, capabilities)
  9. **Resource Management & Optimization** (Process limiting, cleanup, monitoring)
  10. **Synchronization Features** (Optional coordination between clients)
  11. **Error Handling and Recovery** (Failure scenarios, cleanup)
  12. **Advanced Testing and Optimization** (Performance tuning, validation)
  '''

  I have already implemented Phase 1-X. 

  I have developed a plan for implementing Phase X based on this guidance –

  '''
  <THE PHASE X PLAN FROM upgrade_plan.md>
  '''

  Here's a development plan for Phase X, detailing the specific changes needed in the existing files -

  '''
  <THE REVISED IMPLEMENTATION PLAN>
  '''

  Implement this plan now.
```