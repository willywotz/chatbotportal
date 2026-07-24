import asyncio

from fastmcp import Client

async def main():

    # mcp
    # async with Client("http://185.84.161.24/mcp") as client:
    #     print("mcp http transport")
    #     print("ping: ", await client.ping())
    #     print("list_tools: ", await client.list_tools())
    #     print("list_agency: ", await client.call_tool("list_agency"))

    # # sse
    # async with Client("http://185.84.161.24/sse") as client:
    #     print("mcp sse transport")
    #     print("ping: ", await client.ping())
    #     print("list_tools: ", await client.list_tools())
    #     print("list_agency: ", await client.call_tool("list_agency"))

    async with Client("https://chatbotportal.opdc.ai.in.th/mcp") as client:
        print(await client.call_tool("list_agency"))

if __name__ == "__main__":
    asyncio.run(main())

# mcp http transport
# ping:  True
# list_tools:  [Tool(name='list_agency', title=None, description='Return a JSON array of all active government agencies.', inputSchema={'additionalProperties': False, 'properties': {}, 'type': 'object'}, outputSchema={'additionalProperties': True, 'type': 'object'}, icons=None, annotations=None, meta={'fastmcp': {'tags': []}}, execution=None)]
# list_agency:  CallToolResult(content=[TextContent(type='text', text='{"agencies":[{"id":"27f7defe-4b10-4489-ae08-023f0d1805bd","name":"กรมการปกครอง","description":"ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง","connection_type":"API","data_scope":["ทะเบียนราษฎร์","บัตรประจำตัวประชาชน","ทะเบียนบ้าน","การเปลี่ยนชื่อ","สถานะบุคคล"],"endpoint_url":"http://203.154.130.166/dopa/chat","expected_payload":{"query":"{ข้อความคำถามจากผู้ใช้}","session_id":""}},{"id":"0653818b-5b0d-4535-8355-967ff20cbf63","name":"กรมที่ดิน","description":"ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม","connection_type":"API","data_scope":["โฉนดที่ดิน","การจดทะเบียน","ราคาประเมิน","การรังวัด","สิทธิและนิติกรรม"],"endpoint_url":"http://203.154.130.166/dol/chat","expected_payload":{"query":"{ข้อความคำถามจากผู้ใช้}","session_id":""}}],"total":2}', annotations=None, meta=None)], structured_content={'agencies': [{'id': '27f7defe-4b10-4489-ae08-023f0d1805bd', 'name': 'กรมการปกครอง', 'description': 'ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง', 'connection_type': 'API', 'data_scope': ['ทะเบียนราษฎร์', 'บัตรประจำตัวประชาชน', 'ทะเบียนบ้าน', 'การเปลี่ยนชื่อ', 'สถานะบุคคล'], 'endpoint_url': 'http://203.154.130.166/dopa/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}, {'id': '0653818b-5b0d-4535-8355-967ff20cbf63', 'name': 'กรมที่ดิน', 'description': 'ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม', 'connection_type': 'API', 'data_scope': ['โฉนดที่ดิน', 'การจดทะเบียน', 'ราคาประเมิน', 'การรังวัด', 'สิทธิและนิติกรรม'], 'endpoint_url': 'http://203.154.130.166/dol/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}], 'total': 2}, meta=None, data={'agencies': [{'id': '27f7defe-4b10-4489-ae08-023f0d1805bd', 'name': 'กรมการปกครอง', 'description': 'ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง', 'connection_type': 'API', 'data_scope': ['ทะเบียนราษฎร์', 'บัตรประจำตัวประชาชน', 'ทะเบียนบ้าน', 'การเปลี่ยนชื่อ', 'สถานะบุคคล'], 'endpoint_url': 'http://203.154.130.166/dopa/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}, {'id': '0653818b-5b0d-4535-8355-967ff20cbf63', 'name': 'กรมที่ดิน', 'description': 'ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม', 'connection_type': 'API', 'data_scope': ['โฉนดที่ดิน', 'การจดทะเบียน', 'ราคาประเมิน', 'การรังวัด', 'สิทธิและนิติกรรม'], 'endpoint_url': 'http://203.154.130.166/dol/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}], 'total': 2}, is_error=False)

# mcp sse transport
# ping:  True
# list_tools:  [Tool(name='list_agency', title=None, description='Return a JSON array of all active government agencies.', inputSchema={'additionalProperties': False, 'properties': {}, 'type': 'object'}, outputSchema={'additionalProperties': True, 'type': 'object'}, icons=None, annotations=None, meta={'fastmcp': {'tags': []}}, execution=None)]
# list_agency:  CallToolResult(content=[TextContent(type='text', text='{"agencies":[{"id":"27f7defe-4b10-4489-ae08-023f0d1805bd","name":"กรมการปกครอง","description":"ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง","connection_type":"API","data_scope":["ทะเบียนราษฎร์","บัตรประจำตัวประชาชน","ทะเบียนบ้าน","การเปลี่ยนชื่อ","สถานะบุคคล"],"endpoint_url":"http://203.154.130.166/dopa/chat","expected_payload":{"query":"{ข้อความคำถามจากผู้ใช้}","session_id":""}},{"id":"0653818b-5b0d-4535-8355-967ff20cbf63","name":"กรมที่ดิน","description":"ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม","connection_type":"API","data_scope":["โฉนดที่ดิน","การจดทะเบียน","ราคาประเมิน","การรังวัด","สิทธิและนิติกรรม"],"endpoint_url":"http://203.154.130.166/dol/chat","expected_payload":{"query":"{ข้อความคำถามจากผู้ใช้}","session_id":""}}],"total":2}', annotations=None, meta=None)], structured_content={'agencies': [{'id': '27f7defe-4b10-4489-ae08-023f0d1805bd', 'name': 'กรมการปกครอง', 'description': 'ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง', 'connection_type': 'API', 'data_scope': ['ทะเบียนราษฎร์', 'บัตรประจำตัวประชาชน', 'ทะเบียนบ้าน', 'การเปลี่ยนชื่อ', 'สถานะบุคคล'], 'endpoint_url': 'http://203.154.130.166/dopa/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}, {'id': '0653818b-5b0d-4535-8355-967ff20cbf63', 'name': 'กรมที่ดิน', 'description': 'ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม', 'connection_type': 'API', 'data_scope': ['โฉนดที่ดิน', 'การจดทะเบียน', 'ราคาประเมิน', 'การรังวัด', 'สิทธิและนิติกรรม'], 'endpoint_url': 'http://203.154.130.166/dol/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}], 'total': 2}, meta=None, data={'agencies': [{'id': '27f7defe-4b10-4489-ae08-023f0d1805bd', 'name': 'กรมการปกครอง', 'description': 'ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง', 'connection_type': 'API', 'data_scope': ['ทะเบียนราษฎร์', 'บัตรประจำตัวประชาชน', 'ทะเบียนบ้าน', 'การเปลี่ยนชื่อ', 'สถานะบุคคล'], 'endpoint_url': 'http://203.154.130.166/dopa/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}, {'id': '0653818b-5b0d-4535-8355-967ff20cbf63', 'name': 'กรมที่ดิน', 'description': 'ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม', 'connection_type': 'API', 'data_scope': ['โฉนดที่ดิน', 'การจดทะเบียน', 'ราคาประเมิน', 'การรังวัด', 'สิทธิและนิติกรรม'], 'endpoint_url': 'http://203.154.130.166/dol/chat', 'expected_payload': {'query': '{ข้อความคำถามจากผู้ใช้}', 'session_id': ''}}], 'total': 2}, is_error=False)
