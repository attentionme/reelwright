from comfy_adapter import WorkflowAdapter

adapter = WorkflowAdapter("workflow_profile.json")

adapter.set_many(
    prompt=(
        "a red sports car driving on a coastal road at sunset, "
        "cinematic, slow camera pan, warm light, high detail"
    ),
    seed=123456789,
    duration=5.0,
    aspect_ratio="16:9 (Widescreen)",
    megapixels=1,
)

path = adapter.run_once()
print("生成文件：", path)