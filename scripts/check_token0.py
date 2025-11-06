import json

data = json.load(open('token_graph_data.json', encoding='utf-8'))
t0 = [t for t in data['tokens'] if t['id'] == 0][0]
t1 = [t for t in data['tokens'] if t['id'] == 1][0]

print('Token 0 bbox:', t0['bbox'])
print('Token 1 bbox:', t1['bbox'])

center_y0 = (t0['bbox'][1] + t0['bbox'][3]) / 2
center_y1 = (t1['bbox'][1] + t1['bbox'][3]) / 2
center_x0 = (t0['bbox'][0] + t0['bbox'][2]) / 2
center_x1 = (t1['bbox'][0] + t1['bbox'][2]) / 2

dy = abs(center_y1 - center_y0)
dx = abs(center_x1 - center_x0)

print(f'Distancia Y: {dy:.4f}')
print(f'Distancia X: {dx:.4f}')

overlap_x = max(0, min(t0['bbox'][2], t1['bbox'][2]) - max(t0['bbox'][0], t1['bbox'][0]))
print(f'Overlap X: {overlap_x:.4f}')

token0_width = t0['bbox'][2] - t0['bbox'][0]
print(f'Token 0 width: {token0_width:.4f}')
print(f'ortho_threshold_x = max(0.05, {token0_width:.4f} * 1.5) = {max(0.05, token0_width * 1.5):.4f}')

print(f'abs(dx) < ortho_threshold_x? {abs(dx):.4f} < {max(0.05, token0_width * 1.5):.4f} = {abs(dx) < max(0.05, token0_width * 1.5)}')
print(f'dy > 0.005? {dy:.4f} > 0.005 = {dy > 0.005}')

