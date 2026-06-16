// functions/api/generate-image.js
export async function onRequestPost(context) {
  const { request, env } = context;
  
  try {
    const data = await request.json();
    const prompt = data.prompt || '';
    const size = data.size || '1024*1024';
    
    if (!prompt.trim()) {
      return new Response(JSON.stringify({ success: false, error: '请输入图片描述' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 使用阿里图像生成
    const result = await callDashScopeImage(prompt, size, env.DASHSCOPE_API_KEY);
    return new Response(JSON.stringify(result), {
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ success: false, error: error.message }), {
      headers: { 'Content-Type': 'application/json' },
      status: 500
    });
  }
}

async function callDashScopeImage(prompt, size, apiKey) {
  if (!apiKey) return { success: false, error: 'DashScope API Key 未配置' };
  
  try {
    // 提交异步任务
    const submitResponse = await fetch('https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'X-DashScope-Async': 'enable'
      },
      body: JSON.stringify({
        model: 'qwen-image-plus',
        input: { prompt },
        parameters: { size, use_raw_prompt: true }
      })
    });
    
    const submitData = await submitResponse.json();
    const taskId = submitData.output?.task_id || submitData.task_id;
    
    if (!taskId) {
      return { success: false, error: submitData.message || '未获取到任务ID' };
    }

    // 轮询任务结果
    for (let i = 0; i < 20; i++) {
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      const pollResponse = await fetch(`https://dashscope.aliyuncs.com/api/v1/tasks/${taskId}`, {
        headers: { 'Authorization': `Bearer ${apiKey}` }
      });
      
      const pollData = await pollResponse.json();
      const status = pollData.output?.task_status;
      
      if (status === 'SUCCEEDED') {
        const results = pollData.output?.results || [];
        const imageUrls = results.map(r => r.url).filter(Boolean);
        
        return {
          success: true,
          image_urls: imageUrls,
          model: 'qwen-image-plus',
          provider: 'dashscope'
        };
      } else if (status === 'FAILED' || status === 'ERROR') {
        return { success: false, error: pollData.output?.message || '图片生成失败' };
      }
    }
    
    return { success: false, error: '图片生成超时' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}