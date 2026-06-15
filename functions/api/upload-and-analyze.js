// functions/api/upload-and-analyze.js
export async function onRequestPost(context) {
  const { request, env } = context;
  
  try {
    const data = await request.json();
    const image = data.image || '';
    const question = data.question || '请描述这张图片';
    
    if (!image) {
      return new Response(JSON.stringify({ success: false, error: '没有上传图片' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 使用阿里视觉模型
    const result = await callDashScopeVL(image, question, env.DASHSCOPE_API_KEY);
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

async function callDashScopeVL(imageBase64, question, apiKey) {
  if (!apiKey) return { success: false, error: 'DashScope API Key 未配置' };
  
  try {
    const imageUrl = imageBase64.startsWith('data:') 
      ? imageBase64 
      : `data:image/jpeg;base64,${imageBase64}`;
    
    const response = await fetch('https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'qwen-vl-max',
        input: {
          prompt: question,
          image_url: imageUrl
        },
        parameters: { temperature: 0.7 }
      })
    });
    
    const data = await response.json();
    
    if (data.output && data.output.text) {
      return {
        success: true,
        response: data.output.text,
        model: 'qwen-vl-max',
        provider: 'dashscope'
      };
    }
    
    return { success: false, error: data.message || '视觉模型请求失败' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}