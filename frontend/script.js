import Vapi from 'https://esm.sh/@vapi-ai/web@2.5.2';

document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const loadingState = document.getElementById('loading-state');
    const readyState = document.getElementById('ready-state');
    const activeState = document.getElementById('active-state');
    const errorState = document.getElementById('error-state');
    const errorMessage = document.getElementById('error-message');
    const startBtn = document.getElementById('start-btn');
    const endBtn = document.getElementById('end-btn');
    const greeting = document.getElementById('greeting');
    const subtitle = document.getElementById('subtitle');

    // 1. Extract Full Hostname
    let hostnameToMatch = window.location.hostname;

    // If localhost, allow URL param for easy testing, fallback to a dummy domain
    if (hostnameToMatch === "localhost" || hostnameToMatch === "127.0.0.1") {
        const urlParams = new URLSearchParams(window.location.search);
        hostnameToMatch = urlParams.get('company') || "test.fernsystemsai.com";
    }

    let vapi = null;

    // 2. Fetch Token from Backend
    // IMPORTANT: Change this to your deployed backend URL in production
    const backendUrl = "https://voice-token-api-678003405884.us-east4.run.app";

    async function fetchToken() {
        try {
            const response = await fetch(`${backendUrl}/api/generate-token?company=${encodeURIComponent(hostnameToMatch)}`);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || "Failed to fetch agent configuration.");
            }

            const data = await response.json();

            // Initialize Vapi with the securely vended Public Key from the backend.
            // This ensures NO API keys are hardcoded in the frontend source code.
            vapi = new Vapi(data.vapi_public_key);

            // Update UI with Airtable data
            greeting.textContent = `Welcome, ${data.firstName}!`;
            subtitle.textContent = `We've prepared an agent focused on your role as ${data.jobTitle}.`;

            // Update header logo text
            const headerLogo = document.getElementById('header-company-name');
            if (headerLogo) {
                headerLogo.textContent = data.companyName;
            }

            // Setup Vapi Event Listeners inside fetchToken so they attach to the newly created instance
            vapi.on('call-start', () => {
                console.log("Call started");
                showState(activeState);
            });

            vapi.on('call-end', () => {
                console.log("Call ended");
                showState(readyState);
                subtitle.textContent = "Call ended. You can start again when ready.";
            });

            vapi.on('error', (e) => {
                console.error("Vapi Error:", e);
                showError("Call error occurred. Please refresh the page.");
            });

            // Store configuration for the start button
            window.vapiConfig = {
                assistantId: data.assistant_id,
                overrides: {
                    variableValues: {
                        companyName: data.companyName,
                        jobTitle: data.jobTitle
                    }
                }
            };

            showState(readyState);

        } catch (error) {
            console.error("Token Fetch Error:", error);
            showError("Could not connect to backend. " + error.message);
        }
    }

    // Utility: Show specific state
    function showState(stateElement) {
        [loadingState, readyState, activeState, errorState].forEach(el => {
            el.classList.remove('active');
            el.classList.add('hidden');
        });
        stateElement.classList.remove('hidden');
        stateElement.classList.add('active');
    }

    // Utility: Show error
    function showError(msg) {
        errorMessage.textContent = msg;
        showState(errorState);
    }



    // 4. Setup Buttons
    startBtn.addEventListener('click', () => {
        if (!vapi) {
            showError("Agent not initialized. Please refresh.");
            return;
        }
        try {
            // Start the Vapi call using the assistant ID and pass the dynamic Airtable variables
            vapi.start(window.vapiConfig.assistantId, window.vapiConfig.overrides);
        } catch (error) {
            console.error("Failed to start Vapi:", error);
            showError("Failed to start the call.");
        }
    });

    endBtn.addEventListener('click', () => {
        vapi.stop();
    });

    // Kickoff the fetch on page load
    fetchToken();
});
