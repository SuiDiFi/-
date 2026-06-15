// functions/api/chat.js
export async function onRequestPost(context) {
  const { request, env } = context;
  
  try {
    const data = await request.json();
    const prompt = data.prompt || '';
    const temperature = data.temperature || 0.7;
    
    if (!prompt.trim()) {
      return new Response(JSON.stringify({ success: false, error: '请输入问题' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 优先使用阿里 DashScope
    const dashscopeResult = await callDashScope(prompt, temperature, env.DASHSCOPE_API_KEY);
    if (dashscopeResult.success) {
      return new Response(JSON.stringify(dashscopeResult), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 回退到火山引擎
    const volcanoResult = await callVolcano(prompt, temperature, env.VOLC_API_KEY);
    return new Response(JSON.stringify(volcanoResult), {
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ success: false, error: error.message }), {
      headers: { 'Content-Type': 'application/json' },
      status: 500
    });
  }
}

async function callDashScope(prompt, temperature, apiKey) {
  if (!apiKey) return { success: false, error: 'DashScope API Key 未配置' };
  
  try {
    const response = await fetch('https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'qwen-max',
        input: { prompt },
        parameters: { temperature, max_tokens: 2048 }
      })
    });
    
    const data = await response.json();
    
    if (data.output && data.output.text) {
      return {
        success: true,
        response: data.output.text,
        model: 'qwen-max',
        provider: 'dashscope'
      };
    }
    
    return { success: false, error: data.message || 'DashScope 请求失败' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function callVolcano(prompt, temperature, apiKey) {
  if (!apiKey) return { success: false, error: '火山 API Key 未配置' };
  
  try {
    const response = await fetch('https://ark.cn-beijing.volces.com/api/text/completion', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'Doubao-3.5-8K',
        prompt,
        temperature,
        max_tokens: 2048
      })
    });
    
    const data = await response.json();
    
    if (data.choices && data.choices[0]?.text) {
      return {
        success: true,
        response: data.choices[0].text,
        model: 'Doubao-3.5-8K',
        provider: 'volcano'
      };
    }
    
    return { success: false, error: data.message || '火山引擎请求失败' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}