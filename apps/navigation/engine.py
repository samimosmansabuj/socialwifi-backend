


# class CreatePermitRoute(GenericAPIView):
#     permission_classes = [AllowAny]
#     serializer_class = CreatePermitRouteSerializer

#     def extract_route_data(self, data):
#         # permit_file = data.get('permit_file')
#         # url = "http://10.10.7.98:8001/api/ocr/extract/"
#         # payload = {
#         #     "file": permit_file
#         # }
#         # response = requests.post(url, json=payload)
#         # if response.status_code != 200:
#         #     return None
#         # response_data = response.json()

#         response_data = {
#             "success": True,
#             "route_information": {
#                 "start_location": "Rock Rapids, Lyon County, Iowa",
#                 "end_location": "Hancock, Iowa",
#                 "route_segments": [
#                     "IA-9, Rock Rapids, Iowa",
#                     "US-75, Sioux Center, Iowa",
#                     "IA-9, Rock Rapids, Iowa",
#                     "US-59, Sanborn, Iowa",
#                     "US-18, Sanborn, Iowa",
#                     "IA-4, Emmetsburg, Iowa",
#                     "IA-3, Pocahontas, Iowa",
#                     "US-69, Belmond, Iowa",
#                     "B62, Hancock, Iowa"
#                 ],
#                 "intersection": [
#                     "IA-9 and US-75, Sioux Center, Iowa",
#                     "US-75 and IA-9, Rock Rapids, Iowa",
#                     "IA-9 and US-59, Sanborn, Iowa",
#                     "US-59 and US-18, Sanborn, Iowa",
#                     "US-18 and IA-4, Emmetsburg, Iowa",
#                     "IA-4 and IA-3, Pocahontas, Iowa",
#                     "IA-3 and US-69, Belmond, Iowa",
#                     "US-69 and B62, Hancock, Iowa"
#                 ],
#                 "permit_type": "Oversize / Overweight Single Trip"
#             }
#         }
#         if not response_data.get('success') and not response_data.get('route_information'):
#             return None
#         return response_data.get('route_information')

#     def demo_extract_route_data(self):
#         return {
#             "start_location": "Rock Rapids, Lyon County, Iowa",
#             "end_location": "Hancock, Iowa",
#             "route_segments": [
#                 "IA-9, Rock Rapids, Iowa",
#                 "US-75, Sioux Center, Iowa",
#                 "IA-9, Rock Rapids, Iowa",
#                 "US-59, Sanborn, Iowa",
#                 "US-18, Sanborn, Iowa",
#                 "IA-4, Emmetsburg, Iowa",
#                 "IA-3, Pocahontas, Iowa",
#                 "US-69, Belmond, Iowa",
#                 "B62, Hancock, Iowa"
#             ],
#             # "intersection": [
#             #     "IA-9 and US-75, Sioux Center, Iowa",
#             #     "US-75 and IA-9, Rock Rapids, Iowa",
#             #     "IA-9 and US-59, Sanborn, Iowa",
#             #     "US-59 and US-18, Sanborn, Iowa",
#             #     "US-18 and IA-4, Emmetsburg, Iowa",
#             #     "IA-4 and IA-3, Pocahontas, Iowa",
#             #     "IA-3 and US-69, Belmond, Iowa",
#             #     "US-69 and B62, Hancock, Iowa"
#             # ],
#             "intersection": [
#                 "KS-179 and KS-44 near Anthony, Kansas",
#                 "KS-44 and KS-2 near Harper, Kansas",
#                 "KS-2 and US-160 near Medicine Lodge, Kansas",
#                 "US-160 and KS-2 near Harper, Kansas",
#                 "KS-2 and KS-42 near Norwich, Kansas",
#                 "KS-42 and I-235 near Wichita, Kansas",
#                 "I-235 and I-135 near Wichita, Kansas",
#                 "I-135 and US-50 near Newton, Kansas",
#                 "US-50 and I-35 near Emporia, Kansas",
#                 "I-35 and I-435 near Kansas City, Kansas"
#             ],
#             "permit_type": "Oversize / Overweight Single Trip"
#         }

#     def get_intersection_lat_lng(self, address_list: list):
#         print(f"Getting Lat/Lng for addresses {len(address_list)}:", address_list)
#         address_list_lat_lng = []
#         for address in address_list:
#             url = "https://maps.googleapis.com/maps/api/geocode/json"
#             params = {
#                 "address": address,
#                 "key": os.getenv("google_map_api_key")
#             }
#             response = requests.get(url, params=params)
#             data = response.json()
#             if data["status"] == "OK":
#                 location = data["results"][0]["geometry"]["location"]
#                 address_list_lat_lng.append(f"{location['lat']},{location['lng']}")
#         return address_list_lat_lng

#     def post(self, request):
#         try:
#             data = request.data
#             # serializer = CreatePermitRouteSerializer(data=data)
#             # serializer.is_valid(raise_exception=True)
#             # permit_document = serializer.validated_data['permit_document']

#             # route_data = self.extract_route_data(serializer.validated_data)
#             # route_data = self.demo_extract_route_data()
#             # print("Extracted Route Data:", route_data)

#             # waypoints = self.get_intersection_lat_lng(route_data['intersection'])
#             waypoints = ['37.1521327,-98.0393131', '37.2393188,-98.03934989999999', '37.2831739,-98.01936839999999', '37.4591939,-97.7899252', '37.6336974,-97.4333948', '37.6769172,-97.4020811', '38.0315724,-97.3265117', '38.4107659,-96.13573989999999']
#             print("Waypoints with Lat/Lng:", waypoints)


#             return Response(
#                 {
#                     "success": True,
#                     "message": "Permit route created successfully",
#                     "data": {
#                         "start_location": '37.15220130000001,-98.0301635',
#                         "end_location": '39.059472,-94.6280881',
#                         "waypoints": waypoints,
#                         "permit_type": data.get('permit_type', 'Unknown'),
#                     },
#                 },
#                 status=status.HTTP_201_CREATED
#             )
#         except Exception as e:
#             return Response(
#                 {"error": str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
