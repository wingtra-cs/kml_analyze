import xmltodict
import requests
import matplotlib.pyplot as plt
import numpy as np
import pydeck as pdk
import streamlit as st
import pandas as pd
import geopandas as gpd
from scipy.interpolate import griddata
from osgeo import gdal
from shapely.geometry import Point, LineString

def interpolate_raster(file, lat, lon):

    f = gdal.Open(file)
    band = f.GetRasterBand(1)
    
    # Get Raster Information
    transform = f.GetGeoTransform()
    res = transform[1]
    
    # Define point position as row and column in raster
    column = (lon - transform[0]) / transform[1]
    row = (lat - transform[3]) / transform[5]
    
    # Create a 3 x 3 grid of surrounding the point
    surround_data = (band.ReadAsArray(np.floor(column-1), np.floor(row-1), 3, 3))
    lon_c = transform[0] + np.floor(column) * res
    lat_c = transform[3] - np.floor(row) * res
    
    # Extract geoid undulation values of the 3 x 3 grid
    count = -1
    pos = np.zeros((9,2))
    surround_data_v = np.zeros((9,1))
    
    for k in range(-1,2):
        for j in range(-1,2):
            count += 1
            pos[count] = (lon_c+j*res, lat_c-k*res)
            surround_data_v[count] = surround_data[k+1,j+1]
    
    # Do a cubic interpolation of surrounding data and extract value at point
    interp_val = griddata(pos, surround_data_v, (lon, lat), method='cubic')

    return interp_val[0]

def convert2agl(lat, lon, masl):
    elev = []
    
    south = min(lat) - 0.005
    north = max(lat) + 0.005
    west = min(lon) - 0.005
    east = max(lon) + 0.0051
    api_key = '9650231c82589578832a8851f1692a2e'

    with st.spinner('Converting to AGL...'):
        try:
            req = 'https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south=' + str(south) + '&north=' + str(north) + '&west=' + str(west) + '&east=' + str(east) + '&outputFormat=GTiff&API_Key=' + api_key
            resp = requests.get(req)
            open('raster.tif', 'wb').write(resp.content)
        except:
            st.error('No SRTM data in the area. AGL computation is not possible.')
            st.stop()
           
        for la, lo, h in zip(lat, lon, masl):     
            terrain = interpolate_raster('raster.tif', la, lo)
            if terrain > h:
                elev.append(0)
            else:
                elev.append(h - terrain)
    
    st.success('Conversion successful.')
    
    return elev

def main():   
    # Application Formatting
    
    st.set_page_config(layout="wide")
    
    st.title('Maximum AGL Computation')
    
    st.sidebar.image('./logo.png', width = 260)
    st.sidebar.markdown('#')
    st.sidebar.write('The application computes for the maximum AGL of a mission based on the given flight trajectory.')
    st.sidebar.write('The flight trajectory needs to be a KML file generated from AirData.')
    st.sidebar.markdown('#')
    st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')
    # Upload button for Images
    
    uploaded_file = st.file_uploader('Select the KML file from AirData.', accept_multiple_files=False)
    uploaded = False
    format_check = False
    
    # Open the KML file
    if uploaded_file is not None:
        uploaded = True
        st.cache_data.clear()
    
    if uploaded:
        if uploaded_file.name.split('.')[-1] == 'kml':
            format_check = True
            
            kml_dict = xmltodict.parse(uploaded_file.read())
            
            try:       
                coord_list = kml_dict['kml']['Document']['Placemark'][1]['LineString']['coordinates'].split('\n')
            except:
                st.write('Incorrect KML type uploaded.')
                format_check = False
        
        else: 
            format_check = False
            st.write('Uploaded file is not a KML.')
    
        if not format_check:
            st.error('Uploaded file incorrect. Please upload the KML file from AirData.')
            st.stop()
        
        st.success('File Check Successful.')
        
        lat = []
        lon = []
        masl = []
        points = []
        
        for coord in coord_list:
            lon.append(float(coord.split(',')[0]))
            lat.append(float(coord.split(',')[1]))
            masl.append(float(coord.split(',')[2])) 
            points.append(Point(lon[-1],lat[-1]))
        
        agl = convert2agl(lat, lon, masl)
        
        idx_max = agl.index(max(agl))
        lat_max = lat[idx_max]
        lon_max = lon[idx_max]
        max_data = [[lat_max, lon_max]]
        line = LineString(points)
        gdf = gpd.GeoDataFrame({'Name':['Trajectory'], 'geometry':line})
        df = pd.DataFrame(max_data, columns=['lat', 'lon'])
        
        st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/satellite-streets-v11',
        initial_view_state=pdk.ViewState(
            latitude=lat_max,
            longitude=lon_max,
            zoom=16,
            pitch=0,
         ),
         layers=[
             pdk.Layer(
                 'GeoJsonLayer',
                 data=gdf['geometry'],
                 get_line_color='[232, 78, 14]',
                 get_line_width=5
             ),
            pdk.Layer(
                'ScatterplotLayer',
                data=df,
                get_position='[lon, lat]',
                get_fill_color='[255,255,255]',
                get_radius=10,
                get_line_color='[232, 78, 14]',
                get_line_width='5',
                opacity=0.7,
                pickable=True
            ),
             ],
         ))
        
        
        fig, ax = plt.subplots()
        fig.set_size_inches(20, 8)
        ax.plot(range(0,len(agl)), agl, lw=5, color='#E84E0E')
        ax.tick_params(axis='both', which='major', labelsize=20)
        ax.set_xlabel('Time from Power Up (seconds)', size=20, fontweight='bold')
        ax.set_ylabel('AGL (meters)', size=20, fontweight='bold')
        ax.axvline(x=idx_max, color='k', lw=0.8, ls='--')
        ax.axhline(y=max(agl), color='k', lw=0.8, ls='--')
        max_y = int(max(agl)+10)
        ax.set_yticks(range(0, max_y, int(max_y/10)))
        ax.set_ylim([0,int(max_y)+10])
        ax.set_xlim([0, int(len(lat))+5])
        
        st.pyplot(fig)
        
        st.markdown(f'Maximum Altitude Above Ground: **{round(max(agl),4)} meters**.')

if __name__ == "__main__":
    main()