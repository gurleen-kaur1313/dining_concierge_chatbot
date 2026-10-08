(function() {
  var BOT_ICON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>';
  var ERROR_TEXT = 'Oops, something went wrong. Please try again.';

  var messages = document.getElementById('messages');
  var form = document.getElementById('composer');
  var input = document.getElementById('message-input');
  var sendBtn = document.getElementById('send-btn');
  var suggestions = document.getElementById('suggestions');
  var busy = false;

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, who) {
    var row = document.createElement('div');
    row.className = 'row ' + who;

    if (who === 'bot') {
      var avatar = document.createElement('div');
      avatar.className = 'avatar';
      avatar.innerHTML = BOT_ICON;
      row.appendChild(avatar);
    }

    var wrap = document.createElement('div');
    wrap.className = 'bubble-wrap';

    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;  // textContent so user/bot text can never inject HTML

    var time = document.createElement('span');
    time.className = 'time';
    time.textContent = timeNow();

    wrap.appendChild(bubble);
    wrap.appendChild(time);
    row.appendChild(wrap);
    messages.appendChild(row);
    scrollToBottom();
  }

  function showTyping() {
    var row = document.createElement('div');
    row.className = 'row bot typing';
    row.innerHTML = '<div class="avatar">' + BOT_ICON + '</div>' +
      '<div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
    messages.appendChild(row);
    scrollToBottom();
    return row;
  }

  function callChatbotApi(message) {
    // params, body, additionalParams
    return sdk.chatbotPost({}, {
      messages: [{
        type: 'unstructured',
        unstructured: {
          text: message
        }
      }]
    }, {});
  }

  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value || input.value.trim() === '';
  }

  function sendMessage(text) {
    text = text.trim();
    if (!text || busy) {
      return;
    }
    suggestions.classList.add('hidden');
    addMessage(text, 'user');
    input.value = '';
    autoResize();
    setBusy(true);

    var typing = showTyping();

    callChatbotApi(text)
      .then(function(response) {
        var data = response.data || {};
        var replies = (data.messages || []).filter(function(m) {
          return m.type === 'unstructured' && m.unstructured && m.unstructured.text;
        });
        typing.remove();
        if (replies.length === 0) {
          addMessage(ERROR_TEXT, 'bot');
        }
        replies.forEach(function(m) {
          addMessage(m.unstructured.text, 'bot');
        });
      })
      .catch(function(error) {
        console.log('an error occurred', error);
        typing.remove();
        addMessage(ERROR_TEXT, 'bot');
      })
      .then(function() {
        setBusy(false);
        input.focus();
      });
  }

  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    sendMessage(input.value);
  });

  // Enter sends, Shift+Enter adds a new line
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input.value);
    }
  });

  input.addEventListener('input', function() {
    autoResize();
    sendBtn.disabled = busy || input.value.trim() === '';
  });

  suggestions.addEventListener('click', function(e) {
    if (e.target.classList.contains('chip')) {
      sendMessage(e.target.textContent);
    }
  });

  addMessage("Hi there, I'm your personal Concierge. Tell me what you're craving and I'll email you restaurant suggestions.", 'bot');
  input.focus();
})();
